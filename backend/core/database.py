from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

log = logging.getLogger("estatex")


def clog(lead_id: str | None = None) -> logging.LoggerAdapter:
    """Correlation-id logger — every message tagged with [lead=<id>]."""
    return logging.LoggerAdapter(log, {"lead_id": lead_id or "-"})


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------- DB (lazy) ----------

_client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    # Transparent compatibility with test harness monkeypatching of server._db
    srv = sys.modules.get("server")
    if srv is not None and getattr(srv, "_db", None) is not None:
        return srv._db

    if _db is None:
        url = os.environ.get("MONGO_URL")
        if not url:
            raise RuntimeError(
                "MONGO_URL is not set. Copy backend/.env.example to backend/.env "
                "and set MONGO_URL + DB_NAME."
            )
        kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 8000}
        if "mongodb+srv" in url:
            kwargs["tlsCAFile"] = certifi.where()
        _client = AsyncIOMotorClient(url, **kwargs)
        _db = _client[os.environ.get("DB_NAME", "estatex_db")]
    return _db


def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None


class _DBProxy:
    """Deferred handle so ``db.leads`` and ``db["x"]`` work before connect."""

    def __getattr__(self, name: str):
        return getattr(get_db(), name)

    def __getitem__(self, name: str):
        return get_db()[name]


db = _DBProxy()


# ---------- Serialization ----------


def to_mongo(doc: BaseModel) -> dict:
    d = doc.model_dump()
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def from_mongo(cls, doc: dict):
    if not doc:
        return None
    d = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at", "ts"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = datetime.fromisoformat(d[k])
            except Exception:  # noqa: BLE001
                pass
    return cls(**d)
