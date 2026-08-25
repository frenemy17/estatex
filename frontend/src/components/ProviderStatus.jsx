import { useState } from "react";
import { api, providerHint, providerTone } from "../lib/api";
import { usePoll } from "../lib/usePoll";

/**
 * Live integration status. One chip per provider from GET /api/providers:
 * grey = mocked, green = live and healthy, amber = live but the last real call
 * failed (the HTTP status is on hover). This is what makes the difference
 * between "wired up" and "actually calling a third party" visible.
 */
export default function ProviderStatus() {
    const [data, setData] = useState(null);

    usePoll(() => {
        api
            .get("/providers")
            .then((r) => setData(r.data))
            .catch(() => setData(null));
    }, 30000);

    if (!data?.providers?.length) return null;

    const live = data.providers.filter((p) => p.mode === "LIVE").length;

    return (
        <div
            className="flex flex-wrap items-center gap-2 px-4 py-3 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-xl"
            data-testid="provider-status"
        >
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 mr-1">
                Integrations
            </span>

            {data.providers.map((p) => {
                const tone = providerTone(p);
                return (
                    <span
                        key={p.name}
                        title={providerHint(p)}
                        data-testid={`provider-chip-${p.name}`}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border bg-slate-900/70 cursor-help"
                        style={{ borderColor: `${tone.color}40` }}
                    >
                        <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
                        <span className="text-[11px] font-mono text-slate-300">{p.label}</span>
                        <span
                            className="text-[9px] uppercase font-mono tracking-wider"
                            style={{ color: tone.color }}
                        >
                            {tone.label}
                        </span>
                    </span>
                );
            })}

            <span className="ml-auto text-[10px] font-mono text-slate-500">
                {data.demo_mode
                    ? "DEMO_MODE — every provider mocked"
                    : `${live}/${data.providers.length} live`}
            </span>
        </div>
    );
}
