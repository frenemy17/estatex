"""Test harness: an in-memory stand-in for the slice of Motor that EstateX uses.

Why not `httpx.ASGITransport` + a real Mongo? Because the point of this suite is
that a reviewer can clone the repo and run `pytest` — no database, no running
server, no extra pip installs beyond what `requirements.txt` already pins. So we
substitute the database and call the async endpoint functions directly.

The double implements only what `server.py` actually issues: exact-match queries
plus `$in`/`$lt`/`$lte`, the `$set`/`$inc`/`$setOnInsert` update operators with
`upsert`, `sort`/`to_list` cursors, and a single-stage `$group` aggregation. It
deliberately raises on anything else so an unsupported query surfaces as a test
failure rather than a silently empty result.
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force every provider to MOCK before server/providers import and read env.
os.environ["DEMO_MODE"] = "1"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/unused-in-tests")
os.environ.setdefault("DB_NAME", "estatex_test")
os.environ.setdefault("DEMO_CALL_DELAY_SECONDS", "0")
# Quiet hours are wall-clock dependent; tests that care switch them on explicitly.
os.environ.setdefault("QUIET_HOURS_ENABLED", "0")

import pytest  # noqa: E402


# ---------- query matching ----------


def _matches(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                if op == "$in":
                    if value not in operand:
                        return False
                elif op == "$nin":
                    if value in operand:
                        return False
                elif op == "$lt":
                    if value is None or not value < operand:
                        return False
                elif op == "$lte":
                    if value is None or not value <= operand:
                        return False
                elif op == "$gt":
                    if value is None or not value > operand:
                        return False
                elif op == "$gte":
                    if value is None or not value >= operand:
                        return False
                elif op == "$ne":
                    if value == operand:
                        return False
                else:
                    raise NotImplementedError(f"FakeCollection: operator {op}")
        elif value != cond:
            return False
    return True


def _project(doc: dict, projection: dict | None) -> dict:
    out = copy.deepcopy(doc)
    if not projection:
        return out
    excludes = {k for k, v in projection.items() if not v}
    includes = {k for k, v in projection.items() if v}
    if includes:
        keep = includes | {"_id"} - excludes
        out = {k: v for k, v in out.items() if k in keep}
    for k in excludes:
        out.pop(k, None)
    return out


class _Result:
    def __init__(self, matched=0, modified=0, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id


class _Cursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key: str, direction: int = 1):
        self._docs.sort(key=lambda d: (d.get(key) is None, d.get(key)), reverse=direction < 0)
        return self

    async def to_list(self, length: int | None = None):
        return self._docs if length is None else self._docs[:length]


class _Agg:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def to_list(self, length: int | None = None):
        return self._docs if length is None else self._docs[:length]


class FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: list[dict] = []

    # -- reads --
    async def find_one(self, query: dict, projection: dict | None = None):
        for d in self.docs:
            if _matches(d, query):
                return _project(d, projection)
        return None

    def find(self, query: dict | None = None, projection: dict | None = None):
        hits = [_project(d, projection) for d in self.docs if _matches(d, query or {})]
        return _Cursor(hits)

    async def count_documents(self, query: dict | None = None):
        return sum(1 for d in self.docs if _matches(d, query or {}))

    def aggregate(self, pipeline: list[dict]):
        if len(pipeline) != 1 or "$group" not in pipeline[0]:
            raise NotImplementedError("FakeCollection.aggregate: only a single $group")
        spec = pipeline[0]["$group"]
        field = spec["_id"]
        if not (isinstance(field, str) and field.startswith("$")):
            raise NotImplementedError("FakeCollection.aggregate: _id must be a $field")
        field = field[1:]
        buckets: dict = {}
        for d in self.docs:
            buckets.setdefault(d.get(field), 0)
            buckets[d.get(field)] += 1
        out_key = next(k for k in spec if k != "_id")
        return _Agg([{"_id": k, out_key: v} for k, v in buckets.items()])

    # -- writes --
    async def insert_one(self, doc: dict):
        self.docs.append(copy.deepcopy(doc))
        return _Result(upserted_id=doc.get("_id") or doc.get("id"))

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        unknown = set(update) - {"$set", "$inc", "$setOnInsert"}
        if unknown:
            raise NotImplementedError(f"FakeCollection.update_one: {unknown}")
        for d in self.docs:
            if _matches(d, query):
                before = copy.deepcopy(d)
                d.update(copy.deepcopy(update.get("$set") or {}))
                for k, delta in (update.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + delta
                return _Result(matched=1, modified=1 if d != before else 0)
        if not upsert:
            return _Result()
        new: dict = {}
        for k, v in query.items():
            if not isinstance(v, dict):
                new[k] = v
        new.update(copy.deepcopy(update.get("$setOnInsert") or {}))
        new.update(copy.deepcopy(update.get("$set") or {}))
        for k, delta in (update.get("$inc") or {}).items():
            new[k] = delta
        self.docs.append(new)
        return _Result(upserted_id=new.get("_id") or new.get("id") or True)

    async def delete_one(self, query: dict):
        for i, d in enumerate(self.docs):
            if _matches(d, query):
                del self.docs[i]
                return _Result(matched=1)
        return _Result()

    async def delete_many(self, query: dict):
        keep = [d for d in self.docs if not _matches(d, query or {})]
        removed = len(self.docs) - len(keep)
        self.docs = keep
        return _Result(matched=removed)


class FakeDB:
    def __init__(self):
        self._cols: dict[str, FakeCollection] = {}

    def __getattr__(self, name: str) -> FakeCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._cols:
            self._cols[name] = FakeCollection(name)
        return self._cols[name]

    async def command(self, _cmd):
        return {"ok": 1}


@pytest.fixture
def fake_db(monkeypatch):
    """Swap the module-level Mongo handle for an empty in-memory database."""
    import server

    db = FakeDB()
    monkeypatch.setattr(server, "_db", db, raising=False)
    monkeypatch.setattr(server, "_client", None, raising=False)
    server._compiled_graph = None  # rebuild against the fake db
    yield db
    server._compiled_graph = None
