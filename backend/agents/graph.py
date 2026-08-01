"""LangGraph-style micro state-graph with MongoDB checkpointing.

Design mirrors LangGraph's public API (StateGraph, add_node, add_edge,
add_conditional_edges, compile, ainvoke) — but is implemented in ~120 lines
with zero dependencies so the demo has no install-time risk.

Persistence: each `thread_id` (we use lead_id) is stored as one document in
`db.graph_checkpoints`. Interrupts are first-class: a node returns
{"_interrupt": True} to pause; a subsequent ainvoke() with `resume=True`
continues from the last saved node.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

END = "__END__"
log = logging.getLogger("agent-graph")

NodeFn = Callable[[dict], Awaitable[dict]]
RouteFn = Callable[[dict], str]


class MongoCheckpointer:
    def __init__(self, db, collection: str = "graph_checkpoints") -> None:
        self.col = db[collection]

    async def load(self, thread_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": thread_id})
        if not doc:
            return None
        return doc.get("state") or {}

    async def save(self, thread_id: str, state: dict, current: str) -> None:
        await self.col.update_one(
            {"_id": thread_id},
            {"$set": {"state": state, "current_node": current}},
            upsert=True,
        )

    async def clear(self, thread_id: str) -> None:
        await self.col.delete_one({"_id": thread_id})


class StateGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeFn] = {}
        self.edges: dict[str, str] = {}
        self.conditional: dict[str, tuple[RouteFn, dict[str, str]]] = {}
        self.entry: str | None = None

    def add_node(self, name: str, fn: NodeFn) -> None:
        self.nodes[name] = fn

    def add_edge(self, src: str, dst: str) -> None:
        self.edges[src] = dst

    def add_conditional_edges(
        self, src: str, route_fn: RouteFn, mapping: dict[str, str]
    ) -> None:
        self.conditional[src] = (route_fn, mapping)

    def set_entry_point(self, name: str) -> None:
        self.entry = name

    def compile(self, checkpointer: MongoCheckpointer) -> "CompiledGraph":
        assert self.entry is not None, "entry point not set"
        return CompiledGraph(self, checkpointer)


class CompiledGraph:
    def __init__(self, g: StateGraph, cp: MongoCheckpointer) -> None:
        self.g = g
        self.cp = cp

    async def ainvoke(
        self,
        state_in: dict,
        thread_id: str,
        resume: bool = False,
    ) -> dict:
        # Load previous checkpoint (if any) so memory persists across invocations
        prev = await self.cp.load(thread_id) or {}
        state: dict = {**prev, **state_in}

        # Where to start
        if resume:
            # Resume from the node saved by the interrupt (re-run it now that state has approval)
            current = state.get("_interrupt_at") or self.g.entry
            state.pop("_interrupt", None)
            state.pop("_interrupt_at", None)
        else:
            current = self.g.entry

        state.setdefault("trace", [])

        # Bounded loop for safety
        for _ in range(50):
            if current == END:
                break
            node = self.g.nodes.get(current)
            if not node:
                log.error("unknown node %s", current)
                break

            try:
                delta = await node(state)
            except Exception as e:  # noqa: BLE001
                log.exception("node %s failed: %s", current, e)
                state["trace"].append({"step": current, "error": str(e)})
                break

            if delta:
                state.update(delta)

            state["trace"].append(
                {
                    "step": current,
                    **{k: v for k, v in (delta or {}).items() if k in ("thought", "next_action", "requires_approval", "channel", "note")},
                }
            )

            if state.get("_interrupt"):
                state["_interrupt_at"] = current
                await self.cp.save(thread_id, state, current)
                return state

            # Determine next node
            if current in self.g.conditional:
                route_fn, mapping = self.g.conditional[current]
                key = route_fn(state)
                current = mapping.get(key, END)
            elif current in self.g.edges:
                current = self.g.edges[current]
            else:
                current = END

        await self.cp.save(thread_id, state, current)
        return state
