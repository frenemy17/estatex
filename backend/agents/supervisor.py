"""LangGraph-style supervisor + sub-agents for the lead orchestrator (v2).

Flow:
    START -> load_history -> supervisor -> route -> {call|enrich|follow_up|escalate|wait|done}
             (escalate raises an interrupt; approve/reject resumes the graph)

Each node reads/writes a dict-shaped state. Nodes call the LLM via
Groq API (llama-3.3-70b-versatile) and fall back to deterministic
rules if the LLM is unavailable, so the demo never breaks.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import google.generativeai as genai
import requests

from .graph import END, MongoCheckpointer, StateGraph

log = logging.getLogger("supervisor")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

VALID_ACTIONS = {"call", "enrich", "follow_up", "escalate", "wait", "done"}

# ---------- Nodes ----------


def _make_load_history(db):
    async def load_history(state: dict) -> dict:
        lead_id = state["lead_id"]
        lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead:
            return {"thought": "lead not found", "next_action": "done"}
        events = (
            await db.events.find({"lead_id": lead_id}, {"_id": 0})
            .sort("ts", 1)
            .to_list(200)
        )
        return {
            "status": lead["status"],
            "score": lead.get("score", 0),
            "qualification": lead.get("qualification"),
            "attempt_history": lead.get("attempt_history", []),
            "event_count": len(events),
            "opted_out": lead.get("opted_out", False),
            "thought": f"Loaded lead status={lead['status']} score={lead.get('score', 0)} events={len(events)}",
        }

    return load_history


async def _llm_json(session_id: str, system: str, prompt: str, fallback: dict) -> dict:
    """Call LLM (Groq or Gemini) and parse a JSON blob; return fallback on any error."""
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return fallback

    if key.startswith("gsk_"):
        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=10,
            )
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            log.warning("Groq LLM call failed (%s): %s", session_id, e)
            return fallback

    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system)
        resp = await model.generate_content_async(prompt)
        text = resp.text
        cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        return json.loads(match.group(0) if match else cleaned)
    except Exception as e:  # noqa: BLE001
        log.warning("LLM fallback (%s): %s", session_id, e)
        return fallback


def _rule_based_action(state: dict) -> tuple[str, str]:
    status = state.get("status")
    score = state.get("score", 0)
    if state.get("opted_out"):
        return "done", "Lead opted out of contact."
    if status == "NEW":
        return "call", "Fresh lead — call within 5 minutes maximizes conversion."
    if status in ("CALLING", "IN_CONVERSATION"):
        return "wait", "Conversation in progress; do not interrupt."
    if status == "HOT" or score >= 85:
        return "escalate", f"Score {score} — route to senior agent immediately."
    if status == "QUALIFIED":
        return "follow_up", "Qualified lead — send booking prompt."
    if status == "NURTURE":
        return "enrich" if state.get("event_count", 0) < 6 else "follow_up", (
            "Low intent — enrich context first, then drip nurture."
        )
    if status == "BOOKED":
        return "done", "Booked — hand off to human."
    return "wait", "Unknown state."


async def supervisor_node(state: dict) -> dict:
    """LLM-powered next-best-action decision, with rule-based safety net."""
    rule_action, rule_reason = _rule_based_action(state)
    prompt = (
        "You are the supervisor of a real-estate lead orchestrator. "
        f"Lead status={state.get('status')}, score={state.get('score', 0)}, "
        f"qualification={json.dumps(state.get('qualification') or {})}, "
        f"attempts={len(state.get('attempt_history') or [])}, "
        f"opted_out={state.get('opted_out', False)}. "
        "Action Guidelines: "
        "HOT or score >= 85 -> escalate to senior agent; "
        "QUALIFIED -> follow_up with booking prompt; "
        "NURTURE -> enrich or follow_up; "
        "NEW -> call. "
        f"Pick ONE next_action from {sorted(VALID_ACTIONS)}. "
        "Return JSON: {\"next_action\": string, \"reasoning\": string}. "
        f"A safe default is next_action=\"{rule_action}\"."
    )
    fallback = {"next_action": rule_action, "reasoning": rule_reason}
    resp = await _llm_json(
        f"supervisor-{state['lead_id']}",
        "You are a decisive real-estate lead operations supervisor. Respond with JSON only.",
        prompt,
        fallback,
    )
    action = resp.get("next_action")
    if action not in VALID_ACTIONS:
        action = rule_action
        resp["reasoning"] = (resp.get("reasoning") or "") + f" [coerced to {rule_action}]"
    return {
        "next_action": action,
        "thought": resp.get("reasoning") or rule_reason,
    }


def _make_enrichment_agent(db):
    async def enrichment_agent(state: dict) -> dict:
        area = (state.get("qualification") or {}).get("area") or "Downtown"
        prompt = (
            f"Give a two-sentence real-estate briefing on '{area}' relevant to a "
            "prospective buyer. Return JSON: "
            "{\"area\": string, \"median_price\": string, \"hook\": string} "
            "where `hook` is one persuasive sentence a broker could reuse."
        )
        fallback = {
            "area": area,
            "median_price": "n/a",
            "hook": f"{area} inventory is tight — new listings move within 10 days on average.",
        }
        data = await _llm_json(
            f"enrich-{state['lead_id']}",
            "You are a real-estate market researcher. Be concise. Respond with JSON only.",
            prompt,
            fallback,
        )
        # Persist to lead as enrichment
        await db.leads.update_one(
            {"id": state["lead_id"]},
            {"$set": {"enrichment": data}},
        )
        await db.events.insert_one(
            {
                "id": f"ev-enrich-{datetime.now(timezone.utc).timestamp()}",
                "lead_id": state["lead_id"],
                "kind": "enrichment",
                "reason": "enrichment_agent.completed",
                "meta": data,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"enrichment": data, "thought": f"Enriched with area brief for {data.get('area')}."}

    return enrichment_agent


def _make_followup_agent(db, notifier):
    async def followup_agent(state: dict) -> dict:
        lead = await db.leads.find_one({"id": state["lead_id"]}, {"_id": 0})
        if not lead:
            return {"thought": "lead vanished"}
        if lead.get("opted_out"):
            return {"thought": "opted_out — skipping", "channel": "none"}
        q = state.get("qualification") or {}
        prompt = (
            f"Draft a short follow-up for a real-estate lead in status {state.get('status')} "
            f"score {state.get('score', 0)}. Qualification: {json.dumps(q)}. "
            "Return JSON: {\"channel\": \"sms\"|\"email\", \"tone\": string, "
            "\"subject\": string, \"body\": string, \"defer_hours\": integer}."
        )
        fallback = {
            "channel": "sms" if state.get("score", 0) >= 60 else "email",
            "tone": "warm-professional",
            "subject": "Following up on your search",
            "body": f"Hi {lead['name']}, wanted to circle back on {q.get('area') or 'your area'} — I have two matches.",
            "defer_hours": 4 if state.get("score", 0) >= 60 else 24,
        }
        plan = await _llm_json(
            f"followup-{state['lead_id']}",
            "You are a real-estate follow-up copywriter. Concise. JSON only.",
            prompt,
            fallback,
        )
        # Delegate to notifier (respects quiet hours + opt-out)
        # Reconstruct a minimal object with the attributes notifier reads
        class _L:
            pass
        L = _L()
        L.id = lead["id"]
        L.name = lead["name"]
        L.phone = lead["phone"]
        L.email = lead.get("email")
        result = await notifier.send(
            L, plan.get("channel", "sms"), "supervisor_followup", plan
        )
        return {
            "channel": plan.get("channel"),
            "thought": f"Sent {plan.get('channel')} follow-up ({plan.get('tone')}).",
            "followup_plan": plan,
            "followup_result": result,
        }

    return followup_agent


def _make_call_action(dispatch_pipeline):
    async def call_action(state: dict) -> dict:
        dispatch_pipeline(state["lead_id"])
        return {"thought": "Dispatched AI voice pipeline."}

    return call_action


async def escalate_action(state: dict) -> dict:
    # HIGH-STAKES: pause and ask a human before we actually escalate
    if state.get("approved") is True:
        return {
            "thought": "Human approved escalation — routing to senior agent.",
            "requires_approval": False,
            "note": "escalation.approved_and_routed",
        }
    if state.get("approved") is False:
        return {
            "thought": "Human rejected escalation — reverting to nurture.",
            "requires_approval": False,
            "note": "escalation.rejected",
        }
    # First time — interrupt for approval
    return {
        "requires_approval": True,
        "_interrupt": True,
        "thought": "Escalation requires human approval — pausing graph.",
    }


def _make_wait_action(db):
    async def wait_action(state: dict) -> dict:
        next_check = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        await db.leads.update_one(
            {"id": state["lead_id"]},
            {"$set": {"next_check_at": next_check}},
        )
        return {"thought": f"Scheduled next supervisor check at {next_check}."}

    return wait_action


async def done_action(state: dict) -> dict:
    return {"thought": "Graph complete — no further action."}


def route_from_supervisor(state: dict) -> str:
    return state.get("next_action", "wait")


# ---------- Graph builder ----------


def build_supervisor_graph(db, notifier, dispatch_pipeline):
    """Build and compile the supervisor StateGraph (returns CompiledGraph)."""
    g = StateGraph()
    g.add_node("load_history", _make_load_history(db))
    g.add_node("supervisor", supervisor_node)
    g.add_node("call", _make_call_action(dispatch_pipeline))
    g.add_node("enrich", _make_enrichment_agent(db))
    g.add_node("follow_up", _make_followup_agent(db, notifier))
    g.add_node("escalate", escalate_action)
    g.add_node("wait", _make_wait_action(db))
    g.add_node("done", done_action)

    g.set_entry_point("load_history")
    g.add_edge("load_history", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "call": "call",
            "enrich": "enrich",
            "follow_up": "follow_up",
            "escalate": "escalate",
            "wait": "wait",
            "done": "done",
        },
    )
    g.add_edge("call", END)
    g.add_edge("enrich", END)
    g.add_edge("follow_up", END)
    g.add_edge("escalate", END)
    g.add_edge("wait", END)
    g.add_edge("done", END)

    checkpointer = MongoCheckpointer(db, "graph_checkpoints")
    return g.compile(checkpointer)
