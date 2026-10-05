import { useEffect, useState, useRef } from "react";
import { onServerStatusChange, warmupBackend } from "../lib/api";
import { Lightning, CheckCircle, X, CircleNotch } from "@phosphor-icons/react";

/**
 * ServerWakeBanner:
 * Reassuring banner that alerts viewers when Render free tier is cold-starting
 * from inactivity (which typically takes 30-45s), so viewers know the app is
 * working and actively booting rather than frozen or broken.
 */
export default function ServerWakeBanner() {
    const [status, setStatus] = useState("idle"); // "idle" | "waking" | "awake"
    const [elapsed, setElapsed] = useState(0);
    const [dismissed, setDismissed] = useState(false);
    const timerRef = useRef(null);
    const hideTimeoutRef = useRef(null);

    useEffect(() => {
        // Proactively warm up backend upon initial page visit
        warmupBackend();

        const cleanup = onServerStatusChange((detail) => {
            if (detail.status === "waking") {
                setDismissed(false);
                setStatus("waking");
            } else if (detail.status === "awake") {
                setStatus("awake");
                if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
                hideTimeoutRef.current = setTimeout(() => {
                    setStatus("idle");
                }, 2800);
            }
        });

        return () => {
            cleanup();
            if (timerRef.current) clearInterval(timerRef.current);
            if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
        };
    }, []);

    useEffect(() => {
        if (status === "waking") {
            setElapsed(0);
            timerRef.current = setInterval(() => {
                setElapsed((prev) => prev + 1);
            }, 1000);
        } else {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }
    }, [status]);

    if (status === "idle" || dismissed) return null;

    const isWaking = status === "waking";

    return (
        <aside
            data-testid="server-wake-banner"
            aria-live="polite"
            className={`fixed top-4 left-1/2 -translate-x-1/2 z-[100] w-[92vw] max-w-lg transition-all duration-300 ease-out transform ${
                isWaking
                    ? "bg-slate-950/95 border-amber-500/40 shadow-[0_12px_45px_-5px_rgba(245,158,11,0.3)]"
                    : "bg-slate-950/95 border-emerald-500/40 shadow-[0_12px_45px_-5px_rgba(16,185,129,0.3)]"
            } border rounded-2xl p-4 backdrop-blur-2xl text-slate-100 flex flex-col gap-3 float-up`}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                    <div
                        className={`w-9 h-9 rounded-xl grid place-items-center shrink-0 ${
                            isWaking
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        }`}
                    >
                        {isWaking ? (
                            <CircleNotch size={20} weight="bold" className="animate-spin" />
                        ) : (
                            <CheckCircle size={20} weight="fill" />
                        )}
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center gap-2">
                            <span
                                className={`text-[10px] font-mono tracking-wider uppercase px-2 py-0.5 rounded-full border ${
                                    isWaking
                                        ? "bg-amber-400/10 border-amber-400/30 text-amber-300"
                                        : "bg-emerald-400/10 border-emerald-400/30 text-emerald-300"
                                }`}
                            >
                                {isWaking ? "⚡ Render Cloud Boot" : "✓ Connected"}
                            </span>
                            {isWaking && (
                                <span className="text-[10px] font-mono text-slate-400">
                                    {elapsed}s elapsed
                                </span>
                            )}
                        </div>

                        <h4 className="text-sm font-semibold tracking-tight text-slate-50">
                            {isWaking
                                ? "Waking up cloud server..."
                                : "Cloud server is online and active!"}
                        </h4>

                        <p className="text-xs text-slate-400 leading-relaxed">
                            {isWaking
                                ? "Render free tier spins down instances after inactivity. Initial boot takes ~30–45s — your requests will complete automatically."
                                : "Successfully connected to EstateX backend API. All live pipelines and actions are ready."}
                        </p>
                    </div>
                </div>

                <button
                    onClick={() => setDismissed(true)}
                    className="p-1 rounded-md text-slate-500 hover:text-slate-300 transition-colors"
                    aria-label="Dismiss banner"
                    title="Dismiss"
                >
                    <X size={16} />
                </button>
            </div>

            {/* Shimmer loading progress bar during cold start */}
            {isWaking && (
                <div className="w-full h-1 bg-slate-900 rounded-full overflow-hidden relative border border-slate-800/80">
                    <div className="absolute top-0 bottom-0 left-0 w-1/3 bg-gradient-to-r from-amber-400 via-amber-300 to-amber-500 rounded-full animate-shimmer-bar" />
                </div>
            )}
        </aside>
    );
}
