import React, { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { House, ArrowRight, ShieldCheck, Lightning, LockKey, Envelope, User } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { api, setAuthSession } from "../lib/api";

export default function Login() {
    const navigate = useNavigate();
    const location = useLocation();
    const from = location.state?.from?.pathname || "/app";

    const [isRegister, setIsRegister] = useState(false);
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);

    const handleDemoFill = () => {
        setIsRegister(false);
        setEmail("agent@estatex.io");
        setPassword("estatex2026");
        toast.info("Prefilled verified concierge credentials");
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!email || !password) {
            toast.error("Please enter your email and password");
            return;
        }
        if (isRegister && !name.trim()) {
            toast.error("Please provide your name");
            return;
        }

        setLoading(true);
        try {
            if (isRegister) {
                const { data } = await api.post("/auth/register", {
                    name,
                    email,
                    password,
                    role: "agent",
                });
                setAuthSession(data.access_token, data.user);
                toast.success(`Account created! Welcome to EstateX, ${data.user.name}.`);
            } else {
                const { data } = await api.post("/auth/login", {
                    email,
                    password,
                });
                setAuthSession(data.access_token, data.user);
                toast.success(`Welcome back, ${data.user.name}!`);
            }
            navigate(from, { replace: true });
        } catch (err) {
            const detail = err.response?.data?.detail || "Authentication failed";
            toast.error(detail);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between relative overflow-hidden selection:bg-amber-400 selection:text-slate-950" data-testid="login-page">
            {/* Background luxury ambient glow */}
            <div className="absolute -top-40 -left-40 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
            <div className="absolute top-1/3 -right-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

            {/* Header */}
            <header className="px-8 py-6 flex items-center justify-between relative z-10">
                <Link to="/" className="flex items-center gap-2.5 group">
                    <div className="w-8 h-8 rounded-md bg-gradient-to-br from-amber-400 to-amber-600 grid place-items-center transition-transform group-hover:scale-105">
                        <House size={18} weight="fill" className="text-slate-950" />
                    </div>
                    <div>
                        <div className="font-serif text-lg text-slate-50 leading-none">EstateX</div>
                        <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500 mt-1">Agency AI</div>
                    </div>
                </Link>

                <div className="flex items-center gap-4 text-xs font-mono">
                    <Link to="/capture" className="text-slate-400 hover:text-amber-400 transition-colors">
                        Submit Lead Demo &rarr;
                    </Link>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 flex items-center justify-center px-4 py-8 relative z-10">
                <div className="w-full max-w-md bg-slate-900/60 border border-slate-800/80 rounded-2xl p-8 backdrop-blur-xl shadow-2xl">
                    <div className="text-center mb-6">
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/10 border border-amber-400/20 text-amber-300 text-xs font-mono uppercase tracking-wider mb-3">
                            <ShieldCheck size={14} weight="fill" />
                            Autonomous Lead Concierge
                        </div>
                        <h1 className="text-2xl font-serif text-slate-100 font-medium">
                            {isRegister ? "Create Concierge Access" : "Agency Portal Sign In"}
                        </h1>
                        <p className="text-xs text-slate-400 mt-1.5">
                            {isRegister
                                ? "Register an account to review voice qualification and automated lead scoring"
                                : "Sign in to access your inbound pipelines and AI triage logs"}
                        </p>
                    </div>

                    {/* 1-Click Demo Shortcut */}
                    <div className="mb-6 bg-slate-950/70 border border-amber-500/20 rounded-xl p-3.5 flex items-center justify-between gap-3">
                        <div className="text-left">
                            <div className="text-xs font-medium text-amber-300 flex items-center gap-1.5">
                                <Lightning size={14} weight="fill" className="text-amber-400" />
                                Portfolio Evaluator Quick-Access
                            </div>
                            <div className="text-[11px] text-slate-400 mt-0.5">
                                Instant 1-click sign in with pre-seeded demo concierge
                            </div>
                        </div>
                        <Button
                            type="button"
                            size="sm"
                            onClick={handleDemoFill}
                            className="bg-amber-400 hover:bg-amber-300 text-slate-950 text-xs font-semibold shrink-0"
                            data-testid="btn-demo-fill"
                        >
                            Fill Demo
                        </Button>
                    </div>

                    {/* Mode Toggle */}
                    <div className="grid grid-cols-2 p-1 bg-slate-950/60 rounded-lg mb-6 border border-slate-800 text-xs font-medium">
                        <button
                            type="button"
                            onClick={() => setIsRegister(false)}
                            className={`py-2 rounded-md transition-all ${
                                !isRegister
                                    ? "bg-slate-800/90 text-slate-100 shadow"
                                    : "text-slate-400 hover:text-slate-200"
                            }`}
                            data-testid="tab-sign-in"
                        >
                            Sign In
                        </button>
                        <button
                            type="button"
                            onClick={() => setIsRegister(true)}
                            className={`py-2 rounded-md transition-all ${
                                isRegister
                                    ? "bg-slate-800/90 text-slate-100 shadow"
                                    : "text-slate-400 hover:text-slate-200"
                            }`}
                            data-testid="tab-register"
                        >
                            Create Account
                        </button>
                    </div>

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {isRegister && (
                            <div>
                                <Label className="text-xs text-slate-300 mb-1 block">Full Name</Label>
                                <div className="relative">
                                    <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                    <Input
                                        type="text"
                                        placeholder="Alex Vance"
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        className="pl-9 bg-slate-950/50 border-slate-800 text-slate-100 placeholder:text-slate-600 focus-visible:ring-amber-400"
                                        data-testid="input-name"
                                    />
                                </div>
                            </div>
                        )}

                        <div>
                            <Label className="text-xs text-slate-300 mb-1 block">Email Address</Label>
                            <div className="relative">
                                <Envelope size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <Input
                                    type="email"
                                    placeholder="agent@estatex.io"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="pl-9 bg-slate-950/50 border-slate-800 text-slate-100 placeholder:text-slate-600 focus-visible:ring-amber-400"
                                    data-testid="input-email"
                                />
                            </div>
                        </div>

                        <div>
                            <Label className="text-xs text-slate-300 mb-1 block">Password</Label>
                            <div className="relative">
                                <LockKey size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <Input
                                    type="password"
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="pl-9 bg-slate-950/50 border-slate-800 text-slate-100 placeholder:text-slate-600 focus-visible:ring-amber-400"
                                    data-testid="input-password"
                                />
                            </div>
                        </div>

                        <Button
                            type="submit"
                            disabled={loading}
                            className="w-full mt-2 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 text-slate-950 font-semibold py-2.5 transition-all shadow-lg shadow-amber-500/10"
                            data-testid="btn-auth-submit"
                        >
                            {loading ? (
                                "Authenticating…"
                            ) : isRegister ? (
                                <>
                                    Create Agent Account <ArrowRight size={16} weight="bold" className="ml-1.5" />
                                </>
                            ) : (
                                <>
                                    Sign In to Pipeline <ArrowRight size={16} weight="bold" className="ml-1.5" />
                                </>
                            )}
                        </Button>
                    </form>
                </div>
            </main>

            {/* Footer */}
            <footer className="px-8 py-4 text-center text-xs text-slate-600 font-mono relative z-10">
                EstateX Agency AI &bull; Production Real Estate Qualification Platform
            </footer>
        </div>
    );
}
