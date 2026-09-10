from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from core.database import now

LeadStatus = Literal[
    "NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "NURTURE", "HOT", "BOOKED"
]


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Qualification(BaseModel):
    intent: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None
    financing: Optional[str] = None
    area: Optional[str] = None
    reasoning: Optional[str] = None


class Lead(BaseDoc):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    source: str = "web"
    status: LeadStatus = "NEW"
    score: int = 0
    qualification: Optional[Qualification] = None
    transcript: list[dict[str, str]] = Field(default_factory=list)
    supervisor_trace: list[dict[str, Any]] = Field(default_factory=list)
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    enrichment: Optional[dict[str, Any]] = None
    opted_out: bool = False
    pending_approval: bool = False
    next_check_at: Optional[str] = None
    # Set when a real Vapi or Twilio call is in flight and we are waiting on the
    # transcript to be delivered.
    voice_call_id: Optional[str] = None
    awaiting_transcript: bool = False
    # Pins which scripted mock conversation this lead gets. Only set by
    # /api/simulate, so the eval sweep covers every profile exactly.
    sim_profile: Optional[int] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    source: str = "web"
    notes: Optional[str] = None


class Event(BaseDoc):
    lead_id: str
    # transition | note | call | booking | followup | supervisor | enrichment
    # | provider | error
    kind: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    reason: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=now)


class Appointment(BaseDoc):
    lead_id: str
    slot_iso: str
    duration_min: int = 30
    provider: str = "mock-calcom"
    external_id: Optional[str] = None
    status: str = "BOOKED"
    created_at: datetime = Field(default_factory=now)


class ScheduledAction(BaseDoc):
    """A promise to do something later. Drained by run_tick."""

    lead_id: str
    kind: str  # supervisor | notify
    run_at: str  # ISO-8601 UTC; compared lexicographically
    payload: dict[str, Any] = Field(default_factory=dict)
    state: str = "PENDING"  # PENDING | RUNNING | DONE | FAILED | DEAD_LETTER
    attempts: int = 0
    max_attempts: int = 5
    error: Optional[str] = None
    last_error: Optional[str] = None
    dead_letter_reason: Optional[str] = None
    failed_at: Optional[str] = None
    requeued_at: Optional[str] = None
    reason: str = ""
    created_at: datetime = Field(default_factory=now)


class BookSlotRequest(BaseModel):
    slot_iso: str


class GoogleLeadColumn(BaseModel):
    column_id: str
    string_value: Optional[str] = None


class GoogleLeadPayload(BaseModel):
    lead_id: Optional[str] = None
    user_column_data: list[GoogleLeadColumn] = Field(default_factory=list)
    api_version: Optional[str] = None
    form_id: Optional[str] = None
    campaign_id: Optional[str] = None
    google_key: Optional[str] = None
