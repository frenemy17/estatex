import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, STATUS_META, STATUSES, scoreBand } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";

export default function Dashboard() {
    const [leads, setLeads] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [filterCategory, setFilterCategory] = useState("all");
    const [seeding, setSeeding] = useState(false);
    const [showCsvModal, setShowCsvModal] = useState(false);
    const nav = useNavigate();

    async function load() {
        try {
            const { data } = await api.get("/leads");
            setLeads(data);
        } catch {
            toast.error("Failed to load leads");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        load();
        const t = setInterval(load, 3000); // Live poll
        return () => clearInterval(t);
    }, []);

    async function handleSeed() {
        setSeeding(true);
        try {
            const { data } = await api.post("/seed");
            toast.success(`Seeded ${data.created} new leads — AI pipeline dispatched.`);
            load();
        } catch {
            toast.error("Seed failed");
        } finally {
            setSeeding(false);
        }
    }

    const filteredLeads = useMemo(() => {
        return leads.filter((l) => {
            const matchesSearch =
                !searchQuery ||
                l.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                l.phone.includes(searchQuery) ||
                l.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
                l.qualification?.area?.toLowerCase().includes(searchQuery.toLowerCase());

            if (!matchesSearch) return false;

            if (filterCategory === "hot") return l.status === "HOT" || l.score >= 85;
            if (filterCategory === "inflight") return ["CALLING", "IN_CONVERSATION"].includes(l.status);
            if (filterCategory === "booked") return l.status === "BOOKED";
            if (filterCategory === "approval") return l.pending_approval || l.requires_approval;
            return true;
        });
    }, [leads, searchQuery, filterCategory]);

    const columns = useMemo(() => {
        const map = Object.fromEntries(STATUSES.map((s) => [s, []]));
        filteredLeads.forEach((l) => {
            if (map[l.status]) map[l.status].push(l);
        });
        return map;
    }, [filteredLeads]);

    const totalHot = leads.filter((l) => l.status === "HOT" || l.score >= 85).length;
    const totalBooked = leads.filter((l) => l.status === "BOOKED").length;
    const inFlight = leads.filter((l) => ["CALLING", "IN_CONVERSATION"].includes(l.status)).length;
    const pendingApprovals = leads.filter((l) => l.pending_approval || l.requires_approval).length;
    const conversionRate = leads.length > 0 ? Math.round(((totalBooked + totalHot) / leads.length) * 100) : 0;

    return (
        <div className="p-8 space-y-6" data-testid="dashboard">
            {/* Header + KPIs */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 float-up">
                <div>
                    <div className="flex items-center gap-2 mb-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-label text-slate-400">Agency Command Center</span>
                    </div>
                    <h1 className="font-serif text-4xl sm:text-5xl tracking-tight text-slate-50">
                        Live Lead Pipeline
                    </h1>
                    <p className="text-slate-400 mt-2 max-w-xl text-sm leading-relaxed">
                        60-second callbacks, AI buyer qualification, and instant calendar viewings — fully synchronized with your CRM.
                    </p>
                </div>

                {/* KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
                    <Kpi
                        label="In Flight"
                        value={inFlight}
                        color="text-cyan-400"
                        bg="bg-cyan-400/5 border-cyan-500/20"
                        testid="kpi-inflight"
                    />
                    <Kpi
                        label="Hot Leads"
                        value={totalHot}
                        color="text-amber-400"
                        bg="bg-amber-400/5 border-amber-500/20"
                        testid="kpi-hot"
                    />
                    <Kpi
                        label="Booked"
                        value={totalBooked}
                        color="text-emerald-400"
                        bg="bg-emerald-400/5 border-emerald-500/20"
                        testid="kpi-booked"
                    />
                    <Kpi
                        label="Conversion"
                        value={`${conversionRate}%`}
                        color="text-purple-400"
                        bg="bg-purple-400/5 border-purple-500/20"
                        testid="kpi-conversion"
                    />
                </div>
            </div>

            {/* Controls Bar: Search & Quick Filters */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-xl">
                <div className="flex items-center gap-3 w-full sm:w-auto">
                    {/* Search Bar */}
                    <div className="relative w-full sm:w-72">
                        <input
                            type="text"
                            placeholder="Search leads, phones, locations..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-400 transition-colors"
                        />
                    </div>

                    {/* Filter Pills */}
                    <div className="hidden lg:flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs font-mono">
                        <button
                            onClick={() => setFilterCategory("all")}
                            className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                                filterCategory === "all" ? "bg-slate-800 text-slate-100 font-semibold" : "text-slate-400 hover:text-slate-200"
                            }`}
                        >
                            All ({leads.length})
                        </button>
                        <button
                            onClick={() => setFilterCategory("hot")}
                            className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                                filterCategory === "hot" ? "bg-amber-500/20 text-amber-300 font-semibold" : "text-slate-400 hover:text-slate-200"
                            }`}
                        >
                            Hot ({totalHot})
                        </button>
                        <button
                            onClick={() => setFilterCategory("inflight")}
                            className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                                filterCategory === "inflight" ? "bg-cyan-500/20 text-cyan-300 font-semibold" : "text-slate-400 hover:text-slate-200"
                            }`}
                        >
                            In Flight ({inFlight})
                        </button>
                        <button
                            onClick={() => setFilterCategory("booked")}
                            className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                                filterCategory === "booked" ? "bg-emerald-500/20 text-emerald-300 font-semibold" : "text-slate-400 hover:text-slate-200"
                            }`}
                        >
                            Booked ({totalBooked})
                        </button>
                        {pendingApprovals > 0 && (
                            <button
                                onClick={() => setFilterCategory("approval")}
                                className={`px-3 py-1 rounded-md transition-colors cursor-pointer animate-pulse ${
                                    filterCategory === "approval" ? "bg-red-500/20 text-red-300 font-semibold" : "text-red-400 hover:text-red-300"
                                }`}
                            >
                                Approval Pending ({pendingApprovals})
                            </button>
                        )}
                    </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                    <Button
                        onClick={() => nav("/capture")}
                        className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold text-xs px-4 py-2"
                    >
                        + Capture Lead
                    </Button>
                    <Button
                        onClick={() => setShowCsvModal(true)}
                        variant="outline"
                        className="border-slate-800 bg-slate-900/60 text-slate-200 hover:bg-slate-800 text-xs px-3 py-2"
                    >
                        Upload CSV / Excel
                    </Button>
                    <Button
                        onClick={handleSeed}
                        disabled={seeding}
                        variant="outline"
                        className="border-slate-800 bg-slate-900/60 text-slate-400 hover:bg-slate-800 text-xs px-3 py-2"
                    >
                        {seeding ? "Seeding…" : "Seed 15 Leads"}
                    </Button>
                </div>
            </div>

            {/* Kanban Board */}
            <div
                className="flex gap-4 overflow-x-auto pb-4 -mx-8 px-8"
                data-testid="kanban-board"
                style={{ scrollbarWidth: "thin" }}
            >
                {STATUSES.map((s) => (
                    <div
                        key={s}
                        data-testid={`kanban-column-${s.toLowerCase()}`}
                        className="w-80 shrink-0 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-xl flex flex-col"
                    >
                        {/* Column Header */}
                        <div className="px-4 py-3.5 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/40 rounded-t-xl">
                            <div className="flex items-center gap-2">
                                <span
                                    className="w-2.5 h-2.5 rounded-full"
                                    style={{
                                        background: STATUS_META[s].color,
                                        boxShadow: `0 0 10px ${STATUS_META[s].color}60`,
                                    }}
                                />
                                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-200">
                                    {STATUS_META[s].label}
                                </span>
                            </div>
                            <span className="font-mono text-xs text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                                {columns[s].length}
                            </span>
                        </div>

                        {/* Column Content */}
                        <div className="p-3 space-y-3 min-h-[300px] flex-1">
                            {columns[s].length === 0 && (
                                <div className="h-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-slate-800/80 rounded-lg">
                                    <span className="text-xs font-mono uppercase tracking-[0.16em] text-slate-600">
                                        No leads
                                    </span>
                                </div>
                            )}
                            {columns[s].map((l) => (
                                <LeadCard key={l.id} lead={l} onClick={() => nav(`/leads/${l.id}`)} />
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <CsvImportModal open={showCsvModal} onClose={() => setShowCsvModal(false)} onSuccess={load} />
        </div>
    );
}

function Kpi({ label, value, color, bg, testid }) {
    return (
        <div className={`border px-4 py-3 rounded-xl ${bg}`} data-testid={testid}>
            <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">{label}</div>
            <div className={`font-serif text-2xl ${color} leading-tight mt-1`}>{value}</div>
        </div>
    );
}

function LeadCard({ lead, onClick }) {
    const band = scoreBand(lead.score);
    const isCalling = lead.status === "CALLING" || lead.status === "IN_CONVERSATION";
    const needsApproval = lead.pending_approval || lead.requires_approval;

    return (
        <button
            onClick={onClick}
            data-testid={`lead-card-${lead.id}`}
            className={`w-full text-left p-4 rounded-xl bg-slate-900/80 border transition-all duration-200 cursor-pointer ${
                needsApproval
                    ? "border-amber-500/50 bg-amber-500/5 shadow-[0_0_15px_-5px_rgba(251,191,36,0.3)]"
                    : isCalling
                    ? "border-cyan-500/40 bg-cyan-500/5 shadow-[0_0_15px_-5px_rgba(34,211,238,0.3)]"
                    : "border-slate-800/80 hover:border-slate-700 hover:-translate-y-0.5 hover:shadow-lg"
            }`}
        >
            {/* Header: Name & Score */}
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                    <div className="text-sm font-semibold text-slate-100 truncate">
                        {lead.name}
                    </div>

                    <div className="font-mono text-[11px] text-slate-400">
                        {lead.phone}
                    </div>
                </div>

                {/* Score Badge */}
                <div className="text-right shrink-0">
                    <div
                        className="font-mono text-base font-bold leading-none px-2 py-1 rounded border"
                        style={{
                            color: band.color,
                            borderColor: `${band.color}40`,
                            background: `${band.color}10`,
                        }}
                    >
                        {lead.score}
                    </div>
                    <div className="text-[9px] uppercase tracking-wider text-slate-500 mt-1 font-mono">{band.label}</div>
                </div>
            </div>

            {/* Status Badges */}
            {isCalling && (
                <div className="mt-3 flex items-center gap-1.5 text-[10px] font-mono text-cyan-400 bg-cyan-400/10 border border-cyan-400/20 px-2 py-1 rounded-md">
                    AI Call in Progress…
                </div>
            )}

            {needsApproval && (
                <div className="mt-3 flex items-center gap-1.5 text-[10px] font-mono text-amber-300 bg-amber-400/10 border border-amber-400/30 px-2 py-1 rounded-md">
                    Human Approval Required
                </div>
            )}

            {/* Qualification Data */}
            {lead.qualification && (
                <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-1.5">
                    {lead.qualification.intent && (
                        <div className="text-[10px] uppercase font-mono tracking-wider text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded w-max border border-amber-400/20">
                            {lead.qualification.intent}
                        </div>
                    )}

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400 font-mono">
                        {lead.qualification.budget && (
                            <span>{lead.qualification.budget}</span>
                        )}

                        {lead.qualification.timeline && (
                            <span className="truncate">· {lead.qualification.timeline}</span>
                        )}
                    </div>

                    {lead.qualification.area && (
                        <div className="text-[11px] text-slate-500 font-mono truncate pt-0.5">
                            {lead.qualification.area}
                        </div>
                    )}
                </div>
            )}
        </button>
    );
}

/* ---------- CSV / Excel Import Modal ---------- */

function CsvImportModal({ open, onClose, onSuccess }) {
    const [rawText, setRawText] = useState("");
    const [submitting, setSubmitting] = useState(false);

    if (!open) return null;

    function handleFileUpload(e) {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
            setRawText(evt.target?.result || "");
        };
        reader.readAsText(file);
    }

    async function handleImport() {
        if (!rawText.trim()) {
            toast.error("Please select a CSV file or paste lead data");
            return;
        }

        const lines = rawText
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean);

        const parsedLeads = [];
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (i === 0 && (line.toLowerCase().includes("name") || line.toLowerCase().includes("phone"))) {
                continue;
            }
            const parts = line.split(",").map((p) => p.trim().replace(/^["']|["']$/g, ""));
            if (parts.length >= 2) {
                parsedLeads.push({
                    name: parts[0] || "Imported Lead",
                    phone: parts[1] || "+14155550100",
                    email: parts[2] || null,
                    source: parts[3] || "csv_import",
                });
            }
        }

        if (parsedLeads.length === 0) {
            toast.error("No valid lead rows found. Format: Name, Phone, Email, Source");
            return;
        }

        setSubmitting(true);
        try {
            const { data } = await api.post("/leads/bulk", parsedLeads);
            toast.success(`Imported ${data.imported} leads — AI qualification dispatched!`);
            onSuccess();
            onClose();
        } catch {
            toast.error("Bulk import failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
            <div className="w-full max-w-lg bg-slate-950 border border-slate-800 rounded-xl p-6 space-y-5 shadow-2xl relative">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-slate-500 hover:text-slate-200 text-sm font-mono cursor-pointer"
                >
                    ✕
                </button>

                <div>
                    <h2 className="font-serif text-2xl text-slate-50">Bulk Lead Import</h2>
                    <p className="text-slate-400 text-xs mt-1">
                        Upload a CSV / Excel file or paste raw comma-separated lead data.
                    </p>
                </div>

                <div className="space-y-3">
                    <label className="block border-2 border-dashed border-slate-800 hover:border-amber-400/50 bg-slate-900/60 rounded-xl p-6 text-center cursor-pointer transition-colors">
                        <span className="text-xs font-mono text-slate-300 block mb-1">
                            Click to select .CSV / .XLSX file
                        </span>
                        <span className="text-[11px] text-slate-500 block">Format: Name, Phone, Email, Source</span>
                        <input type="file" accept=".csv,.txt,.xlsx,.xls" onChange={handleFileUpload} className="hidden" />
                    </label>

                    <div className="text-center text-xs font-mono text-slate-500 uppercase tracking-widest">— Or Paste Data Below —</div>

                    <textarea
                        rows={5}
                        placeholder={"Jane Doe, +14155550199, jane@example.com, Meta Ads\nJohn Smith, +14155550200, john@example.com, Zillow"}
                        value={rawText}
                        onChange={(e) => setRawText(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-400"
                    />
                </div>

                <div className="flex justify-between items-center pt-2">
                    <Button variant="outline" onClick={onClose} className="border-slate-800 text-slate-400 text-xs">
                        Cancel
                    </Button>
                    <Button
                        onClick={handleImport}
                        disabled={submitting}
                        className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold text-xs px-5 py-2"
                    >
                        {submitting ? "Importing Leads…" : "Import & Run AI Pipeline"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
