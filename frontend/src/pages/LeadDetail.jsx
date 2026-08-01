import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, STATUS_META, scoreBand } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { ArrowLeft, Robot, Brain, CalendarCheck, Phone, Sparkle, Check } from "@phosphor-icons/react";

export default function LeadDetail() {
    const { id } = useParams();
    const nav = useNavigate();
    const [lead, setLead] = useState(null);
    const [events, setEvents] = useState([]);
    const [slots, setSlots] = useState([]);
    const [appts, setAppts] = useState([]);
    const [busy, setBusy] = useState(false);

    async function load() {
        try {
            const [l, ev, ap] = await Promise.all([
                api.get(`/leads/${id}`),
                api.get(`/leads/${id}/events`),
                api.get(`/leads/${id}/appointments`),
            ]);
            setLead(l.data);
            setEvents(ev.data);
            setAppts(ap.data);
        } catch {
            toast.error("Failed to load lead");
        }
    }

    async function loadSlots() {
        const { data } = await api.get(`/leads/${id}/slots`);
        setSlots(data.slots);
    }

    useEffect(() => {
        load();
        loadSlots();
        const t = setInterval(load, 3000);
        return () => clearInterval(t);
    }, [id]);

    async function bookSlot(slot) {
        setBusy(true);
        try {
            await api.post(`/leads/${id}/book`, { slot_iso: slot });
            toast.success("Booked. Handing off to human agent.");
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Booking failed");
        } finally {
            setBusy(false);
        }
    }

    async function runSupervisor() {
        setBusy(true);
        try {
            const { data } = await api.post(`/leads/${id}/supervisor`);
            toast.success(`Supervisor → ${data.next_action}`);
            load();
        } catch {
            toast.error("Supervisor failed");
        } finally {
            setBusy(false);
        }
    }

    async function rerun() {
        setBusy(true);
        try {
            await api.post(`/leads/${id}/rerun`);
            toast.success("Pipeline re-dispatched");
            load();
        } finally {
            setBusy(false);
        }
    }

    async function approve() {
        setBusy(true);
        try {
            await api.post(`/leads/${id}/approve`);
            toast.success("Escalation approved — routed to senior agent.");
            load();
        } catch {
            toast.error("Approve failed");
        } finally {
            setBusy(false);
        }
    }

    async function reject() {
        setBusy(true);
        try {
            await api.post(`/leads/${id}/reject`);
            toast.success("Escalation rejected — reverted to nurture.");
            load();
        } catch {
            toast.error("Reject failed");
        } finally {
            setBusy(false);
        }
    }

    async function optOut() {
        setBusy(true);
        try {
            await api.post(`/leads/${id}/opt-out`);
            toast.success("Lead opted out — no more messages.");
            load();
        } finally {
            setBusy(false);
        }
    }

    if (!lead) return <div className="p-8 text-slate-500">Loading…</div>;

    const band = scoreBand(lead.score);
    const meta = STATUS_META[lead.status];

    return (
        <div className="p-8 space-y-6" data-testid="lead-detail">
            <button
                onClick={() => nav(-1)}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-100 uppercase tracking-[0.2em]"
                data-testid="btn-back"
            >
                <ArrowLeft size={12} /> Back
            </button>

            {lead.pending_approval && (
                <div
                    className="border border-amber-500/40 bg-amber-500/5 rounded-lg p-5 flex items-center justify-between gap-4"
                    data-testid="approval-banner"
                >
                    <div className="min-w-0">
                        <div className="text-label text-amber-400">Human Approval Required</div>
                        <div className="text-sm text-slate-200 mt-1">
                            The AI supervisor wants to <span className="text-amber-300 font-semibold">escalate this lead to a senior agent</span>. Approve or reject before it acts.
                        </div>
                    </div>
                    <div className="flex gap-2 shrink-0">
                        <Button
                            onClick={reject}
                            variant="outline"
                            disabled={busy}
                            className="border-slate-700 bg-slate-900/40 text-slate-300 hover:bg-slate-800"
                            data-testid="btn-reject-escalation"
                        >
                            Reject
                        </Button>
                        <Button
                            onClick={approve}
                            disabled={busy}
                            className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold"
                            data-testid="btn-approve-escalation"
                        >
                            <Check size={14} weight="bold" className="mr-1.5" /> Approve
                        </Button>
                    </div>
                </div>
            )}

            {lead.opted_out && (
                <div className="border border-red-500/40 bg-red-500/5 rounded-lg p-3 text-xs text-red-300" data-testid="opted-out-banner">
                    Lead is opted out — notifications are blocked.
                </div>
            )}

            <div className="grid grid-cols-12 gap-6">
                {/* Left: Lead info + qualification */}
                <div className="col-span-12 lg:col-span-5 space-y-6">
                    <div className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-6">
                        <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                                <div className="text-label">Lead</div>
                                <h1 className="font-serif text-3xl text-slate-50 mt-1">{lead.name}</h1>
                                <div className="font-mono text-xs text-slate-500 mt-1">{lead.phone}</div>
                                {lead.email && <div className="font-mono text-xs text-slate-500">{lead.email}</div>}
                            </div>
                            <div className="text-right">
                                <div className="font-mono text-5xl leading-none" style={{ color: band.color }}>
                                    {lead.score}
                                </div>
                                <div className="text-label mt-1" style={{ color: band.color }}>
                                    {band.label}
                                </div>
                            </div>
                        </div>

                        <div className="mt-6 flex items-center gap-2">
                            <span
                                className="w-2 h-2 rounded-full"
                                style={{ background: meta.color }}
                            />
                            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">
                                {meta.label}
                            </span>
                            <span className="ml-auto text-[10px] font-mono text-slate-500">
                                {new Date(lead.updated_at).toLocaleString()}
                            </span>
                        </div>

                        <div className="mt-6 grid grid-cols-2 gap-3">
                            <QField label="Intent" value={lead.qualification?.intent} />
                            <QField label="Budget" value={lead.qualification?.budget} />
                            <QField label="Timeline" value={lead.qualification?.timeline} />
                            <QField label="Financing" value={lead.qualification?.financing} />
                            <QField label="Area" value={lead.qualification?.area} full />
                        </div>

                        <div className="mt-6 flex gap-2 flex-wrap">
                            <Button
                                onClick={runSupervisor}
                                disabled={busy}
                                variant="outline"
                                className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
                                data-testid="btn-run-supervisor"
                            >
                                <Brain size={14} weight="duotone" className="mr-1.5" /> Run Supervisor
                            </Button>
                            <Button
                                onClick={rerun}
                                disabled={busy}
                                variant="outline"
                                className="border-slate-700 bg-slate-900/40 text-slate-300 hover:bg-slate-800"
                                data-testid="btn-rerun"
                            >
                                <Sparkle size={14} weight="duotone" className="mr-1.5" /> Re-run Pipeline
                            </Button>
                            <Button
                                onClick={optOut}
                                disabled={busy || lead.opted_out}
                                variant="outline"
                                className="border-slate-700 bg-slate-900/40 text-slate-400 hover:bg-slate-800"
                                data-testid="btn-opt-out"
                            >
                                Opt out
                            </Button>
                        </div>
                    </div>

                    {/* Booking */}
                    <div className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <CalendarCheck size={18} weight="duotone" className="text-amber-400" />
                            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-200">
                                Book a Viewing
                            </span>
                        </div>
                        {appts.length > 0 && (
                            <div className="mb-4 space-y-1.5">
                                {appts.map((a) => (
                                    <div
                                        key={a.id}
                                        className="text-xs font-mono flex items-center gap-2 text-emerald-400"
                                        data-testid={`appt-${a.id}`}
                                    >
                                        <Check size={12} weight="bold" />
                                        {new Date(a.slot_iso).toLocaleString()}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="grid grid-cols-3 gap-1.5">
                            {slots.slice(0, 9).map((s) => (
                                <button
                                    key={s}
                                    onClick={() => bookSlot(s)}
                                    disabled={busy}
                                    data-testid={`slot-${s}`}
                                    className="text-[11px] font-mono py-2 px-2 rounded border border-slate-800 bg-slate-900/60 hover:border-amber-400/50 hover:bg-amber-400/5 text-slate-300 transition-colors"
                                >
                                    {new Date(s).toLocaleString(undefined, {
                                        month: "short",
                                        day: "numeric",
                                        hour: "numeric",
                                    })}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Right: Transcript + supervisor trace + events */}
                <div className="col-span-12 lg:col-span-7 space-y-6">
                    <div className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Phone size={18} weight="duotone" className="text-cyan-400" />
                            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-200">
                                AI Conversation Transcript
                            </span>
                        </div>
                        {lead.transcript?.length ? (
                            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-2">
                                {lead.transcript.map((t, i) => (
                                    <div
                                        key={i}
                                        className={`p-2.5 rounded font-mono text-xs ${
                                            t.role === "agent"
                                                ? "bg-cyan-500/5 border border-cyan-500/20 text-cyan-100"
                                                : "bg-slate-900/60 border border-slate-800 text-slate-300 ml-6"
                                        }`}
                                    >
                                        <div className="text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-1">
                                            {t.role === "agent" ? "AI Agent" : lead.name}
                                        </div>
                                        {t.text}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-slate-500 text-sm">No conversation yet — AI is dispatching.</div>
                        )}
                    </div>

                    {lead.supervisor_trace?.length > 0 && (
                        <div className="border border-cyan-500/30 bg-slate-950/60 rounded-lg p-6 shadow-[0_0_40px_-15px_rgba(34,211,238,0.4)]">
                            <div className="flex items-center gap-2 mb-4">
                                <Brain size={18} weight="duotone" className="text-cyan-400" />
                                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
                                    AI Supervisor Reasoning
                                </span>
                            </div>
                            <div className="space-y-2">
                                {lead.supervisor_trace.map((t, i) => (
                                    <div
                                        key={i}
                                        className="border-l-2 border-cyan-500/40 pl-3 py-1"
                                        data-testid={`trace-step-${i}`}
                                    >
                                        <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-mono">
                                            {t.step}
                                            {t.next_action && (
                                                <span className="ml-2 text-amber-400">→ {t.next_action}</span>
                                            )}
                                        </div>
                                        <div className="font-mono text-xs text-slate-300 mt-1">{t.thought}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Robot size={18} weight="duotone" className="text-slate-400" />
                            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-200">
                                Event Audit Log
                            </span>
                        </div>
                        <div className="space-y-1.5 max-h-[240px] overflow-y-auto pr-2">
                            {events.map((e) => (
                                <div
                                    key={e.id}
                                    className="flex items-center gap-3 text-xs font-mono"
                                    data-testid={`event-${e.id}`}
                                >
                                    <span className="text-[10px] text-slate-600 w-32 shrink-0">
                                        {new Date(e.ts).toLocaleString(undefined, {
                                            month: "short",
                                            day: "numeric",
                                            hour: "2-digit",
                                            minute: "2-digit",
                                            second: "2-digit",
                                        })}
                                    </span>
                                    <span className="text-slate-500 uppercase text-[10px] w-20 shrink-0">
                                        {e.kind}
                                    </span>
                                    <span className="text-slate-300 truncate">
                                        {e.from_status && (
                                            <span className="text-slate-500">
                                                {e.from_status} →{" "}
                                            </span>
                                        )}
                                        {e.to_status && (
                                            <span
                                                className="text-slate-100 font-semibold"
                                                style={{ color: STATUS_META[e.to_status]?.color }}
                                            >
                                                {e.to_status}
                                            </span>
                                        )}
                                        {e.reason && (
                                            <span className="text-slate-500 ml-2">· {e.reason}</span>
                                        )}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function QField({ label, value, full }) {
    return (
        <div className={`p-3 rounded border border-slate-800 bg-slate-900/40 ${full ? "col-span-2" : ""}`}>
            <div className="text-label mb-1">{label}</div>
            <div className="font-mono text-xs text-slate-200 truncate">{value || "—"}</div>
        </div>
    );
}
