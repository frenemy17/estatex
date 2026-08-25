import { NavLink, Outlet, useNavigate, Link } from "react-router-dom";
import { House, ChartLineUp, GitBranch, Plus, MagnifyingGlass, SquaresFour } from "@phosphor-icons/react";
import { Button } from "./ui/button";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useState } from "react";
import { useAdminToken } from "./AdminTokenButton";

const nav = [
    { to: "/app", label: "Pipeline", icon: SquaresFour, testid: "nav-pipeline" },
    { to: "/analytics", label: "Analytics", icon: ChartLineUp, testid: "nav-analytics" },
];

export default function Layout() {
    const navigate = useNavigate();
    const [seeding, setSeeding] = useState(false);
    const admin = useAdminToken();

    async function handleSeed() {
        setSeeding(true);
        try {
            const { data } = await api.post("/seed");
            toast.success(`Seeded ${data.created} new leads — AI pipeline dispatched.`);
            setTimeout(() => navigate(0), 800);
        } catch (e) {
            toast.error(
                e?.response?.status === 401 ? "Admin token required to seed" : "Seed failed"
            );
        } finally {
            setSeeding(false);
        }
    }

    return (
        <div className="min-h-screen flex" data-testid="app-layout">
            {/* Sidebar */}
            <aside className="w-64 shrink-0 border-r border-slate-800/80 bg-slate-950/60 backdrop-blur-xl flex flex-col">
                <div className="px-6 py-8">
                    <Link to="/" className="flex items-center gap-2.5 group" data-testid="sidebar-logo">
                        <div className="w-8 h-8 rounded-md bg-gradient-to-br from-amber-400 to-amber-600 grid place-items-center transition-transform group-hover:scale-105">
                            <House size={18} weight="fill" className="text-slate-950" />
                        </div>
                        <div>
                            <div className="font-serif text-lg text-slate-50 leading-none">EstateX</div>
                            <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500 mt-1">Agency AI</div>
                        </div>
                    </Link>
                </div>

                <nav className="px-3 flex-1 space-y-1">
                    {nav.map((n) => (
                        <NavLink
                            key={n.to}
                            to={n.to}
                            end={n.to === "/app"}
                            data-testid={n.testid}
                            className={({ isActive }) =>
                                `group flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                                    isActive
                                        ? "bg-slate-800/60 text-slate-50 border-l-2 border-amber-400"
                                        : "text-slate-400 hover:text-slate-100 hover:bg-slate-900/40 border-l-2 border-transparent"
                                }`
                            }
                        >
                            <n.icon size={18} weight="duotone" />
                            <span>{n.label}</span>
                        </NavLink>
                    ))}
                </nav>

                <div className="p-4 border-t border-slate-800/80">
                    <Button
                        onClick={handleSeed}
                        disabled={seeding || !admin}
                        title={admin ? undefined : "Read-only demo — add the backend ADMIN_TOKEN to enable this"}
                        variant="outline"
                        className="w-full border-slate-800 bg-slate-900/40 text-slate-300 hover:bg-slate-800 hover:text-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        data-testid="btn-seed-leads"
                    >
                        {seeding ? "Seeding…" : "Seed 15 Demo Leads"}
                    </Button>
                </div>
            </aside>

            {/* Main */}
            <main className="flex-1 flex flex-col min-w-0">
                <header className="sticky top-0 z-30 h-16 border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-xl flex items-center justify-between px-8">
                    <div className="flex items-center gap-3 text-slate-400">
                        <MagnifyingGlass size={16} />
                        <span className="text-xs uppercase tracking-[0.24em]">Command Center</span>
                    </div>
                    <Button
                        onClick={() => navigate("/capture")}
                        className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold"
                        data-testid="btn-new-lead"
                    >
                        <Plus size={16} weight="bold" className="mr-1.5" /> New Lead
                    </Button>
                </header>

                <div className="flex-1 min-h-0">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
