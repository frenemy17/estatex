from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

import providers
from core.database import db, now_iso, to_mongo
from core.models import Lead, Qualification
from core.pipeline import run_ai_pipeline
from core.scoring import _fallback_score, classify_score, extract_answers
from core.state_machine import record_event, transition
from core.tick import MAX_SCHEDULED_ATTEMPTS, run_tick
from routes.auth import require_admin

router = APIRouter(tags=["admin"])

FUNNEL_ORDER = ["NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "NURTURE", "HOT", "BOOKED"]

SEED_LEADS = [
    ("Emily Chen", "+14155550101", "emily.chen@example.com"),
    ("Marcus Reed", "+14155550102", "marcus.reed@example.com"),
    ("Priya Sharma", "+919876543210", "priya.s@example.com"),
    ("Diego Alvarez", "+14155550104", "diego.a@example.com"),
    ("Aisha Bello", "+14155550105", "aisha.b@example.com"),
    ("Jonas Weber", "+14155550106", "jonas.w@example.com"),
    ("Sofia Rossi", "+14155550107", "sofia.r@example.com"),
    ("Kenji Tanaka", "+14155550108", "kenji.t@example.com"),
    ("Nadia Al-Farsi", "+14155550109", "nadia.a@example.com"),
    ("Owen Fitzgerald", "+14155550110", "owen.f@example.com"),
    ("Beatrice Laurent", "+14155550111", "bea.l@example.com"),
    ("Riya Kapoor", "+919812345678", "riya.k@example.com"),
    ("Samuel Okafor", "+14155550113", "sam.o@example.com"),
    ("Isabella Costa", "+14155550114", "isabella.c@example.com"),
    ("Theo Nakamura", "+14155550115", "theo.n@example.com"),
]

SIM_LEADS = [
    ("Sim Alpha", "+14155551001", "a1@x.com"),
    ("Sim Bravo", "+14155551002", "a2@x.com"),
    ("Sim Charlie", "+14155551003", "a3@x.com"),
    ("Sim Delta", "+14155551004", "a4@x.com"),
    ("Sim Echo", "+14155551005", "a5@x.com"),
    ("Sim Foxtrot", "+14155551006", "a6@x.com"),
    ("Sim Golf", "+14155551007", "a7@x.com"),
    ("Sim Hotel", "+14155551008", "a8@x.com"),
    ("Sim India", "+14155551009", "a9@x.com"),
    ("Sim Juliet", "+14155551010", "a10@x.com"),
    ("Sim Kilo", "+14155551011", "a11@x.com"),
    ("Sim Lima", "+14155551012", "a12@x.com"),
    ("Sim Mike", "+14155551013", "a13@x.com"),
    ("Sim November", "+14155551014", "a14@x.com"),
    ("Sim Oscar", "+14155551015", "a15@x.com"),
]


@router.post("/tick", dependencies=[Depends(require_admin)])
async def tick(limit: int = 25):
    """Drive one autonomy pass. Called by cron every ~10 minutes."""
    return await run_tick(limit=limit)


@router.get("/queue/dead-letter", dependencies=[Depends(require_admin)])
async def list_dead_letter(limit: int = 50, skip: int = 0):
    """List quarantined dead-letter actions with failure details."""
    cursor = db.scheduled_actions.find({"state": "DEAD_LETTER"}).sort("failed_at", -1)
    if skip:
        cursor = cursor.skip(skip)
    actions = await cursor.to_list(limit)

    lead_ids = list({a.get("lead_id") for a in actions if a.get("lead_id")})
    leads = {}
    if lead_ids:
        lead_docs = await db.leads.find({"id": {"$in": lead_ids}}).to_list(len(lead_ids))
        leads = {
            l["id"]: {
                "name": l.get("name"),
                "phone": l.get("phone"),
                "status": l.get("status"),
            }
            for l in lead_docs
        }

    results = []
    for a in actions:
        results.append(
            {
                "id": a.get("id"),
                "lead_id": a.get("lead_id"),
                "kind": a.get("kind"),
                "attempts": a.get("attempts", 0),
                "max_attempts": a.get("max_attempts", MAX_SCHEDULED_ATTEMPTS),
                "error": a.get("error"),
                "last_error": a.get("last_error") or a.get("error"),
                "failed_at": a.get("failed_at"),
                "dead_letter_reason": a.get("dead_letter_reason"),
                "payload": a.get("payload", {}),
                "lead": leads.get(a.get("lead_id")),
            }
        )
    return {"total": len(results), "actions": results}


@router.post("/queue/dead-letter/{action_id}/retry", dependencies=[Depends(require_admin)])
async def retry_dead_letter(action_id: str):
    """Manually replay/requeue a dead-lettered action."""
    action = await db.scheduled_actions.find_one({"id": action_id, "state": "DEAD_LETTER"})
    if not action:
        raise HTTPException(status_code=404, detail="Dead-letter action not found")

    requeued_at = now_iso()
    await db.scheduled_actions.update_one(
        {"id": action_id},
        {
            "$set": {
                "state": "PENDING",
                "run_at": requeued_at,
                "attempts": 0,
                "last_error": None,
                "requeued_at": requeued_at,
            }
        },
    )
    if action.get("lead_id"):
        await record_event(
            action["lead_id"],
            "operator",
            reason="scheduled.requeued",
            meta={"action_id": action_id, "requeued_at": requeued_at},
        )
    return {"status": "requeued", "action_id": action_id}


@router.get("/analytics")
async def analytics():
    rows = await db.leads.aggregate(
        [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    ).to_list(20)
    counts = {r["_id"]: r["count"] for r in rows if r.get("_id")}
    total = sum(counts.values())
    booked = counts.get("BOOKED", 0)
    return {
        "total": total,
        "booked": booked,
        "qualified": counts.get("QUALIFIED", 0) + counts.get("HOT", 0) + booked,
        "hot": counts.get("HOT", 0),
        "conversion_rate": round((booked / total) * 100, 1) if total else 0.0,
        "funnel": [{"status": s, "count": counts.get(s, 0)} for s in FUNNEL_ORDER],
    }


@router.post("/seed", dependencies=[Depends(require_admin)])
async def seed(bg: BackgroundTasks):
    created = 0
    for name, phone, email in SEED_LEADS:
        if await db.leads.find_one({"phone": phone}):
            continue
        lead = Lead(name=name, phone=phone, email=email, source="seed")
        await db.leads.insert_one(to_mongo(lead))
        await record_event(lead.id, "note", reason="lead.seeded")
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created}


@router.delete("/reset", dependencies=[Depends(require_admin)])
async def reset():
    for coll in (
        "leads",
        "events",
        "appointments",
        "graph_checkpoints",
        "scheduled_actions",
        "webhook_receipts",
        "provider_health",
        "rate_limits",
    ):
        await db[coll].delete_many({})
    return {"ok": True}


@router.post("/simulate", dependencies=[Depends(require_admin)])
async def simulate(bg: BackgroundTasks):
    """Run 15 scripted leads through the pipeline for eval."""
    created = 0
    for i, (name, phone, email) in enumerate(SIM_LEADS):
        if await db.leads.find_one({"phone": phone}):
            continue
        lead = Lead(
            name=name,
            phone=phone,
            email=email,
            source="sim",
            sim_profile=i % providers.MOCK_PROFILE_COUNT,
        )
        await db.leads.insert_one(to_mongo(lead))
        await record_event(
            lead.id, "note", reason="lead.simulated", meta={"profile": lead.sim_profile}
        )
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created, "total": len(SIM_LEADS)}


@router.get("/eval")
async def eval_run():
    docs = await db.leads.find({"source": "sim"}, {"_id": 0}).to_list(100)
    agree = 0
    graded = 0
    hallucinated = 0
    disagreements = []

    for d in docs:
        transcript = d.get("transcript") or []
        if not transcript or d["status"] not in ("QUALIFIED", "HOT", "NURTURE", "BOOKED"):
            continue
        graded += 1
        baseline_q = Qualification(**extract_answers(transcript))
        expected = classify_score(_fallback_score(baseline_q))
        actual = "HOT" if d["status"] == "BOOKED" and expected == "HOT" else d["status"]
        if actual == expected:
            agree += 1
        else:
            disagreements.append(
                {"lead_id": d["id"], "expected": expected, "actual": d["status"], "score": d.get("score")}
            )

        text = " ".join(t.get("text", "") for t in transcript).lower()
        q = d.get("qualification") or {}
        for field_name in ("budget", "area", "timeline"):
            v = (q.get(field_name) or "").lower()
            if v and len(v) > 3 and v not in text:
                hallucinated += 1
                break

    return {
        "graded": graded,
        "agreements": agree,
        "rubric_agreement": round(agree / graded, 3) if graded else 0.0,
        "hallucination_rate": round(hallucinated / graded, 3) if graded else 0.0,
        "booking_rate": round(
            sum(1 for d in docs if d["status"] == "BOOKED") / len(docs), 3
        )
        if docs
        else 0.0,
        "sample_size": len(docs),
        "baseline_only": providers.provider_status("groq")["mode"] == "MOCK",
        "disagreements": disagreements[:10],
    }
