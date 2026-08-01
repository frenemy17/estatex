import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { House, ArrowRight } from "@phosphor-icons/react";

export default function Capture() {
    const nav = useNavigate();
    const [form, setForm] = useState({ name: "", phone: "", email: "", source: "web" });
    const [submitting, setSubmitting] = useState(false);

    async function submit(e) {
        e.preventDefault();
        if (!form.name || !form.phone) {
            toast.error("Name and phone are required");
            return;
        }
        setSubmitting(true);
        try {
            const { data } = await api.post("/lead", form);
            toast.success("Thanks — an AI agent is calling now.");
            setTimeout(() => nav(`/leads/${data.id}`), 900);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="min-h-screen grid lg:grid-cols-2" data-testid="capture-page">
            <div
                className="hidden lg:block relative"
                style={{
                    backgroundImage:
                        "linear-gradient(rgba(2,6,23,0.7), rgba(2,6,23,0.95)), url('https://images.pexels.com/photos/30211366/pexels-photo-30211366.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940')",
                    backgroundSize: "cover",
                    backgroundPosition: "center",
                }}
            >
                <div className="absolute inset-0 p-16 flex flex-col justify-between">
                    <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-md bg-gradient-to-br from-amber-400 to-amber-600 grid place-items-center">
                            <House size={18} weight="fill" className="text-slate-950" />
                        </div>
                        <div className="font-serif text-xl text-slate-50">EstateX Realty</div>
                    </div>
                    <div>
                        <h2 className="font-serif text-5xl text-slate-50 leading-tight">
                            The right home, called back in minutes.
                        </h2>
                        <p className="text-slate-400 mt-4 max-w-md text-sm">
                            Leave your details and one of our AI concierges will call, qualify your search, and book
                            a viewing on your calendar — before you finish your coffee.
                        </p>
                    </div>
                </div>
            </div>

            <div className="flex items-center justify-center p-8">
                <form
                    onSubmit={submit}
                    className="w-full max-w-md border border-slate-800/80 bg-slate-950/60 rounded-lg p-8 space-y-5"
                    data-testid="capture-form"
                >
                    <div>
                        <div className="text-label">Lead Capture</div>
                        <h1 className="font-serif text-3xl text-slate-50 mt-2">Tell us what you're looking for.</h1>
                    </div>

                    <Field label="Full name" required>
                        <input
                            data-testid="input-name"
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            className="w-full bg-slate-900/60 border border-slate-800 rounded-md px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-400/40 focus:border-cyan-400/40"
                            placeholder="e.g. Emily Chen"
                        />
                    </Field>

                    <Field label="Phone" required>
                        <input
                            data-testid="input-phone"
                            value={form.phone}
                            onChange={(e) => setForm({ ...form, phone: e.target.value })}
                            className="w-full bg-slate-900/60 border border-slate-800 rounded-md px-3 py-2.5 text-sm font-mono text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-400/40 focus:border-cyan-400/40"
                            placeholder="+1 415 555 0123"
                        />
                    </Field>

                    <Field label="Email">
                        <input
                            data-testid="input-email"
                            type="email"
                            value={form.email}
                            onChange={(e) => setForm({ ...form, email: e.target.value })}
                            className="w-full bg-slate-900/60 border border-slate-800 rounded-md px-3 py-2.5 text-sm font-mono text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-400/40 focus:border-cyan-400/40"
                            placeholder="you@example.com"
                        />
                    </Field>

                    <Button
                        type="submit"
                        disabled={submitting}
                        className="w-full bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold"
                        data-testid="btn-submit-lead"
                    >
                        {submitting ? "Sending…" : "Get a call in 5 minutes"} <ArrowRight size={14} weight="bold" className="ml-1.5" />
                    </Button>

                    <button
                        type="button"
                        onClick={() => nav("/app")}
                        className="w-full text-center text-[11px] uppercase tracking-[0.24em] text-slate-500 hover:text-slate-300"
                        data-testid="btn-goto-dashboard"
                    >
                        Or view the pipeline dashboard
                    </button>
                </form>
            </div>
        </div>
    );
}

function Field({ label, required, children }) {
    return (
        <label className="block space-y-1.5">
            <span className="text-label">
                {label} {required && <span className="text-amber-400">*</span>}
            </span>
            {children}
        </label>
    );
}
