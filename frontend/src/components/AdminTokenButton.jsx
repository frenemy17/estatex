import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, getAdminToken, onAdminTokenChange, setAdminToken } from "../lib/api";
import { Button } from "./ui/button";

/** Subscribe to the stored admin token so every consumer re-renders on change. */
export function useAdminToken() {
    const [token, setToken] = useState(getAdminToken);
    useEffect(() => onAdminTokenChange(() => setToken(getAdminToken())), []);
    return token;
}

/**
 * Read-only by default. The admin token lives in localStorage and is attached to
 * every request by the axios interceptor in lib/api.js — nothing is baked into
 * the bundle, so the public demo can stay browsable without exposing the token
 * that guards seed / reset / bulk import.
 */
export default function AdminTokenButton() {
    const token = useAdminToken();
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState("");
    const [checking, setChecking] = useState(false);

    async function save() {
        const value = draft.trim();
        if (!value) {
            toast.error("Paste the ADMIN_TOKEN value from the backend environment");
            return;
        }
        setChecking(true);
        setAdminToken(value);
        try {
            // /tick is admin-only and idempotent, so it doubles as a token check.
            await api.post("/tick");
            toast.success("Admin unlocked — seed, import and reset are live.");
            setOpen(false);
            setDraft("");
        } catch (e) {
            if (e?.response?.status === 401) {
                setAdminToken("");
                toast.error("Token rejected by the backend.");
            } else {
                toast.success("Token saved (backend did not confirm — check /api/health).");
                setOpen(false);
                setDraft("");
            }
        } finally {
            setChecking(false);
        }
    }

    return (
        <>
            <Button
                onClick={() => (token ? setAdminToken("") : setOpen(true))}
                variant="outline"
                data-testid="btn-admin-token"
                title={
                    token
                        ? "Admin mode — click to return to read-only"
                        : "Read-only demo — add the backend ADMIN_TOKEN to enable writes"
                }
                className={`text-xs px-3 py-2 border ${
                    token
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                        : "border-slate-800 bg-slate-900/60 text-slate-400 hover:bg-slate-800"
                }`}
            >
                <span
                    className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                        token ? "bg-emerald-400" : "bg-slate-500"
                    }`}
                />
                {token ? "Admin" : "Read-only"}
            </Button>

            {open && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
                    <div className="w-full max-w-md bg-slate-950 border border-slate-800 rounded-xl p-6 space-y-4 shadow-2xl relative">
                        <button
                            onClick={() => setOpen(false)}
                            className="absolute top-4 right-4 text-slate-500 hover:text-slate-200 text-sm font-mono cursor-pointer"
                        >
                            ✕
                        </button>

                        <div>
                            <h2 className="font-serif text-2xl text-slate-50">Unlock write actions</h2>
                            <p className="text-slate-400 text-xs mt-1 leading-relaxed">
                                Seeding, CSV import, reset and the autonomy tick require the backend{" "}
                                <span className="font-mono text-slate-300">ADMIN_TOKEN</span>. It is stored
                                in this browser only and sent as{" "}
                                <span className="font-mono text-slate-300">X-Admin-Token</span>.
                            </p>
                        </div>

                        <input
                            type="password"
                            autoFocus
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && save()}
                            placeholder="ADMIN_TOKEN"
                            data-testid="input-admin-token"
                            className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-400"
                        />

                        <div className="flex justify-between items-center pt-1">
                            <Button
                                variant="outline"
                                onClick={() => setOpen(false)}
                                className="border-slate-800 text-slate-400 text-xs"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={save}
                                disabled={checking}
                                data-testid="btn-save-admin-token"
                                className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold text-xs px-5 py-2"
                            >
                                {checking ? "Verifying…" : "Save & verify"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
