import { useState } from "react";
import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const COLORS = {
    NEW: "#60a5fa",
    CALLING: "#22d3ee",
    IN_CONVERSATION: "#818cf8",
    QUALIFIED: "#34d399",
    NURTURE: "#fbbf24",
    HOT: "#ef4444",
    BOOKED: "#d946ef",
};

export default function Analytics() {
    const [data, setData] = useState(null);

    usePoll(() => {
        api
            .get("/analytics")
            .then((r) => setData(r.data))
            .catch(() => {});
    }, 15000);

    if (!data) return <div className="p-8 text-slate-500">Loading…</div>;

    return (
        <div className="p-8 space-y-8" data-testid="analytics-page">
            <div>
                <div className="text-label">Analytics</div>
                <h1 className="font-serif text-4xl sm:text-5xl tracking-tight text-slate-50 mt-1">
                    Every lead, every second.
                </h1>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Metric label="Total Leads" value={data.total} accent="text-slate-100" testid="metric-total" />
                <Metric
                    label="Conversion Rate"
                    value={`${data.conversion_rate}%`}
                    accent="text-amber-400"
                    testid="metric-conversion"
                />
                <Metric label="Qualified" value={data.qualified} accent="text-emerald-400" testid="metric-qualified" />
                <Metric label="Booked" value={data.booked} accent="text-fuchsia-400" testid="metric-booked" />
            </div>

            <div className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-6">
                <div className="text-label mb-4">Funnel by Status</div>
                <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={data.funnel} margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                            <XAxis
                                dataKey="status"
                                tick={{ fill: "#94a3b8", fontFamily: "IBM Plex Mono", fontSize: 10 }}
                                axisLine={{ stroke: "#1e293b" }}
                                tickLine={false}
                            />
                            <YAxis
                                tick={{ fill: "#64748b", fontFamily: "IBM Plex Mono", fontSize: 10 }}
                                axisLine={{ stroke: "#1e293b" }}
                                tickLine={false}
                            />
                            <Tooltip
                                cursor={{ fill: "rgba(148,163,184,0.05)" }}
                                contentStyle={{
                                    background: "rgba(15,23,42,0.95)",
                                    border: "1px solid #1e293b",
                                    borderRadius: 6,
                                    fontFamily: "IBM Plex Mono",
                                    fontSize: 12,
                                }}
                            />
                            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                                {data.funnel.map((f) => (
                                    <Cell key={f.status} fill={COLORS[f.status]} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}

function Metric({ label, value, accent, testid }) {
    return (
        <div
            data-testid={testid}
            className="border border-slate-800/80 bg-slate-950/40 rounded-lg p-5"
        >
            <div className="text-label">{label}</div>
            <div className={`font-serif text-4xl mt-2 leading-none ${accent}`}>{value}</div>
        </div>
    );
}
