import { useEffect, useState } from "react";
import { api, STATUS_META, scoreBand } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { GitBranch, Robot, Brain } from "@phosphor-icons/react";

export default function Compare() {
    const [leads, setLeads] = useState([]);
    const [pickA, setPickA] = useState(null);
    const [pickB, setPickB] = useState(null);
    const [traceA, setTraceA] = useState(null);
    const [traceB, setTraceB] = useState(null);

    useEffect(() => {
        api.get("/leads").then((r) => {
            setLeads(r.data);
            if (r.data.length >= 2) {
                setPickA(r.data[0].id);
                setPickB(r.data[1].id);
            }
        });
    }, []);

    async function runV2(leadId, setTrace) {
        try {
            const { data } = await api.post(`/leads/${leadId}/supervisor`);
            setTrace(data);
            toast.success(`V2 → ${data.next_action}`);
        } catch {
            toast.error("Supervisor failed");
        }
    }

    const A = leads.find((l) => l.id === pickA);
    const B = leads.find((l) => l.id === pickB);

    return (
        <div className="p-8 space-y-6" data-testid="compare-page">
            <div className="flex items-center gap-3">
                <GitBranch size={22} weight="duotone" className="text-cyan-400" />
                <div>
                    <div className="text-label">Side-by-side</div>
                    <h1 className="font-serif text-4xl text-slate-50 mt-1">V1 Rules vs V2 Supervisor</h1>
                </div>
            </div>
            <p className="text-slate-400 text-sm max-w-2xl">
                V1 executes a deterministic pipeline (call → qualify → route). V2 runs the same lead through a
                LangGraph-style supervisor that reasons about next-best-action and logs its trace. Same lead,
                different brains.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Panel
                    title="V1 · Deterministic"
                    icon={Robot}
                    color="text-amber-400"
                    accent="border-amber-400/30"
                    leads={leads}
                    pick={pickA}
                    onPick={setPickA}
                    lead={A}
                    isV2={false}
                    testid="panel-v1"
                />
                <Panel
                    title="V2 · Supervisor Agent"
                    icon={Brain}
                    color="text-cyan-400"
                    accent="border-cyan-400/30"
                    leads={leads}
                    pick={pickB}
                    onPick={setPickB}
                    lead={B}
                    isV2
                    trace={traceB}
                    onRun={() => pickB && runV2(pickB, setTraceB)}
                    testid="panel-v2"
                />
            </div>
        </div>
    );
}

function Panel({ title, icon: Icon, color, accent, leads, pick, onPick, lead, isV2, trace, onRun, testid }) {
    return (
        <div
            className={`border ${accent} bg-slate-950/50 rounded-lg p-6 space-y-4`}
            data-testid={testid}
        >
            <div className="flex items-center gap-2">
                <Icon size={20} weight="duotone" className={color} />
                <span className={`text-xs font-semibold uppercase tracking-[0.2em] ${color}`}>{title}</span>
            </div>

            <select
                value={pick || ""}
                onChange={(e) => onPick(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 font-mono"
                data-testid={`${testid}-select`}
            >
                <option value="">Choose lead…</option>
                {leads.map((l) => (
                    <option key={l.id} value={l.id}>
                        {l.name} — {l.status} ({l.score})
                    </option>
                ))}
            </select>

            {lead && (
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <span className="text-slate-100 font-semibold">{lead.name}</span>
                        <span
                            className="font-mono text-2xl"
                            style={{ color: scoreBand(lead.score).color }}
                        >
                            {lead.score}
                        </span>
                    </div>
                    <div className="text-xs font-mono text-slate-400">
                        Status:{" "}
                        <span style={{ color: STATUS_META[lead.status]?.color }}>{lead.status}</span>
                    </div>

                    {!isV2 && (
                        <div className="border-l-2 border-amber-400/40 pl-3 py-1 space-y-1">
                            <div className="text-[10px] uppercase tracking-[0.2em] text-amber-400 font-mono">
                                Rule Engine
                            </div>
                            <div className="font-mono text-xs text-slate-300">
                                Score {lead.score} ≥ 70 →{" "}
                                <span className="text-emerald-400">QUALIFIED</span>. Route via fixed template.
                            </div>
                        </div>
                    )}

                    {isV2 && (
                        <>
                            <Button
                                onClick={onRun}
                                variant="outline"
                                className="w-full border-cyan-500/30 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
                                data-testid={`${testid}-run`}
                            >
                                <Brain size={14} weight="duotone" className="mr-1.5" />
                                Run Supervisor
                            </Button>
                            {trace && (
                                <div className="space-y-2 pt-2">
                                    <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-mono">
                                        Reasoning Trace → {trace.next_action}
                                        {trace.requires_approval && (
                                            <span className="ml-2 text-amber-400">[APPROVAL NEEDED]</span>
                                        )}
                                    </div>
                                    {trace.trace.map((t, i) => (
                                        <div
                                            key={i}
                                            className="border-l-2 border-cyan-500/40 pl-3 py-1"
                                        >
                                            <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-mono">
                                                {t.step}
                                            </div>
                                            <div className="font-mono text-xs text-slate-300">{t.thought}</div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
