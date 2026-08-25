import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import {
    House,
    ArrowRight,
    Phone,
    Brain,
    CalendarCheck,
    Lightning,
    ShieldCheck,
    Robot,
    ChartLineUp,
    GitBranch,
    Sparkle,
    ArrowUpRight,
    CheckCircle,
    Waveform,
    UserCircle,
} from "@phosphor-icons/react";

/**
 * Landing page — the wow moment.
 * Composition:
 *   - Sticky glass nav
 *   - Hero (left copy, right animated live-pipeline mock)
 *   - Trust ribbon
 *   - Problem strip
 *   - How-it-works (3 steps)
 *   - Live agent conversation preview
 *   - Feature grid (6 cards)
 *   - V1 vs V2 split
 *   - Metrics band
 *   - Final CTA
 *   - Footer
 */
export default function Landing() {
    const [showOnboarding, setShowOnboarding] = useState(false);
    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 overflow-x-hidden" data-testid="landing-page">
            <Nav onStartTrial={() => setShowOnboarding(true)} />
            <Hero onStartTrial={() => setShowOnboarding(true)} />
            <TrustRibbon />
            <ProblemStrip />
            <HowItWorks />
            <AgentPreview />
            <FeatureGrid />
            <ArchitectureSplit />
            <MetricsBand />
            <FinalCTA onStartTrial={() => setShowOnboarding(true)} />
            <Footer />
            <AgencyOnboardingModal open={showOnboarding} onClose={() => setShowOnboarding(false)} />
        </div>
    );
}

/* ---------- Nav ---------- */

function Nav({ onStartTrial }) {
    return (
        <header className="sticky top-0 z-40 border-b border-slate-800/50 bg-slate-950/70 backdrop-blur-xl">
            <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
                <Link to="/" className="flex items-center gap-2.5" data-testid="nav-logo">
                    <div className="w-8 h-8 rounded-md bg-gradient-to-br from-amber-400 to-amber-600 grid place-items-center">
                        <House size={18} weight="fill" className="text-slate-950" />
                    </div>
                    <div className="leading-none">
                        <div className="font-serif text-lg">EstateX</div>
                        <div className="text-[9px] uppercase tracking-[0.24em] text-slate-500 mt-0.5">Agency AI</div>
                    </div>
                </Link>
                <nav className="hidden md:flex items-center gap-8 text-sm text-slate-400">
                    <a href="#how" className="hover:text-slate-100 transition-colors">How it works</a>
                    <a href="#features" className="hover:text-slate-100 transition-colors">Capabilities</a>
                    <a href="#architecture" className="hover:text-slate-100 transition-colors">Integrations</a>
                </nav>
                <div className="flex items-center gap-2">
                    <Link
                        to="/app"
                        className="text-sm text-slate-300 hover:text-slate-100 px-3 py-1.5"
                        data-testid="nav-open-app"
                    >
                        Agency Dashboard
                    </Link>
                    <button
                        onClick={onStartTrial}
                        data-testid="nav-cta"
                        className="text-sm font-semibold bg-amber-400 hover:bg-amber-300 text-slate-950 px-4 py-2 rounded-md flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                        Start Free Trial <ArrowRight size={14} weight="bold" />
                    </button>
                </div>
            </div>
        </header>
    );
}

/* ---------- Hero ---------- */

function Hero({ onStartTrial }) {
    return (
        <section className="relative overflow-hidden">
            <div className="absolute inset-0 grid-lines opacity-40 radial-fade" />
            <div
                className="absolute inset-0 pointer-events-none"
                style={{
                    background:
                        "radial-gradient(ellipse 60% 60% at 30% 30%, rgba(34,211,238,0.08), transparent), radial-gradient(ellipse 50% 60% at 70% 70%, rgba(251,191,36,0.06), transparent)",
                }}
            />
            <div className="relative max-w-7xl mx-auto px-6 lg:px-10 py-20 lg:py-28 grid lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 space-y-8">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-slate-800 bg-slate-900/60 text-[11px] uppercase tracking-[0.24em] text-slate-400 float-up" style={{ animationDelay: "0ms" }}>
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        B2B AI Platform for Real Estate Agencies
                    </div>
                    <h1 className="font-serif text-5xl sm:text-6xl lg:text-7xl leading-[1.02] tracking-tight float-up" style={{ animationDelay: "80ms" }}>
                        Your first responder,
                        <br />
                        <span className="shimmer-text italic">before the lead cools.</span>
                    </h1>
                    <p className="text-slate-400 text-lg max-w-xl leading-relaxed float-up" style={{ animationDelay: "160ms" }}>
                        Turn web forms and ad inquiries into booked property viewings instantly.
                        Our AI Concierge calls leads back in under 60 seconds, filters out tire-kickers,
                        and schedules qualified buyers straight onto your calendar — 24/7.
                    </p>
                    <div className="flex flex-wrap items-center gap-3 float-up" style={{ animationDelay: "240ms" }}>
                        <button
                            onClick={onStartTrial}
                            data-testid="hero-cta-primary"
                            className="group inline-flex items-center gap-2 bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-5 py-3 rounded-md transition-all hover:-translate-y-[1px] cursor-pointer"
                        >
                            Start 14-Day Agency Trial
                            <ArrowRight size={16} weight="bold" className="transition-transform group-hover:translate-x-0.5" />
                        </button>
                        <Link
                            to="/capture"
                            data-testid="hero-cta-secondary"
                            className="inline-flex items-center gap-2 border border-slate-800 bg-slate-900/40 hover:bg-slate-800 text-slate-200 px-5 py-3 rounded-md text-sm"
                        >
                            Test AI Concierge Live
                            <ArrowUpRight size={14} weight="bold" />
                        </Link>
                    </div>
                    <div className="flex items-center gap-6 pt-2 text-xs text-slate-500 float-up" style={{ animationDelay: "320ms" }}>
                        <span className="flex items-center gap-1.5">
                            <CheckCircle size={14} weight="duotone" className="text-emerald-400" />
                            &lt; 60 sec first response
                        </span>
                        <span className="flex items-center gap-1.5">
                            <CheckCircle size={14} weight="duotone" className="text-emerald-400" />
                            24/7 · 365
                        </span>
                        <span className="flex items-center gap-1.5">
                            <CheckCircle size={14} weight="duotone" className="text-emerald-400" />
                            Human-approved escalations
                        </span>
                    </div>
                </div>

                <div className="lg:col-span-6 float-up" style={{ animationDelay: "300ms" }}>
                    <LivePipelineMock />
                </div>
            </div>
        </section>
    );
}

/* ---------- Animated Live Pipeline mock ---------- */

function LivePipelineMock() {
    const stages = ["NEW", "CALLING", "IN CONV", "QUALIFIED", "BOOKED"];
    const [stage, setStage] = useState(0);
    const [score, setScore] = useState(0);

    useEffect(() => {
        const t = setInterval(() => {
            setStage((s) => (s + 1) % stages.length);
        }, 2200);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        if (stage <= 2) {
            let n = 0;
            const target = stage === 2 ? 87 : 0;
            const t = setInterval(() => {
                n += 3;
                if (n >= target) {
                    setScore(target);
                    clearInterval(t);
                } else {
                    setScore(n);
                }
            }, 40);
            return () => clearInterval(t);
        } else {
            setScore(87);
        }
    }, [stage]);

    return (
        <div className="relative">
            {/* Ambient glow */}
            <div className="absolute -inset-4 bg-gradient-to-br from-cyan-500/10 via-transparent to-amber-500/10 blur-3xl" />

            <div className="relative border border-slate-800/80 bg-slate-950/70 backdrop-blur-xl rounded-xl p-6 shadow-[0_40px_120px_-30px_rgba(34,211,238,0.35)]">
                {/* Header */}
                <div className="flex items-center justify-between mb-5">
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1">
                            <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                            <span className="w-2.5 h-2.5 rounded-full bg-amber-400/70" />
                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
                        </div>
                        <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500 font-mono ml-3">
                            estatex · live pipeline
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        streaming
                    </div>
                </div>

                {/* Card */}
                <div className="border border-slate-800 bg-slate-900/60 rounded-lg p-4">
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-full bg-slate-800 grid place-items-center">
                                <UserCircle size={22} weight="duotone" className="text-slate-400" />
                            </div>
                            <div>
                                <div className="text-sm font-semibold text-slate-100">Priya Sharma</div>
                                <div className="text-[11px] font-mono text-slate-500">+91 98765 43210</div>
                            </div>
                        </div>
                        <div className="text-right">
                            <div className={`font-mono text-3xl leading-none transition-colors ${score >= 70 ? "text-emerald-400" : "text-slate-300"}`}>
                                {score}
                            </div>
                            <div className="text-[9px] uppercase tracking-[0.2em] text-slate-500 mt-1">score</div>
                        </div>
                    </div>

                    {/* Progress rail */}
                    <div className="mt-5">
                        <div className="flex justify-between mb-2">
                            {stages.map((s, i) => (
                                <div
                                    key={s}
                                    className={`text-[9px] font-mono uppercase tracking-[0.14em] transition-colors ${
                                        i <= stage ? "text-slate-200" : "text-slate-600"
                                    }`}
                                >
                                    {s}
                                </div>
                            ))}
                        </div>
                        <div className="relative h-1 rounded-full bg-slate-800 overflow-hidden">
                            <div
                                className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-400 to-emerald-400 transition-all duration-700"
                                style={{ width: `${((stage + 1) / stages.length) * 100}%` }}
                            />
                        </div>
                        <div className="flex justify-between mt-1">
                            {stages.map((_, i) => (
                                <div
                                    key={i}
                                    className={`w-2 h-2 rounded-full transition-all ${
                                        i === stage
                                            ? "bg-cyan-400 ring-pulse"
                                            : i < stage
                                            ? "bg-emerald-400"
                                            : "bg-slate-700"
                                    }`}
                                />
                            ))}
                        </div>
                    </div>
                </div>

                {/* Live agent chat */}
                <div className="mt-5 space-y-2 text-xs font-mono">
                    <ChatLine role="agent" text="Hi Priya, this is Ava from EstateX Realty." delay={0} />
                    <ChatLine role="lead" text="Hi — quick, what neighborhoods have inventory?" delay={200} />
                    <ChatLine role="agent" text="Downtown & East Village. Budget range?" delay={400} />
                    <ChatLine role="lead" text="$650-750k, pre-approved, moving in 2 months." delay={600} />
                </div>

                {/* Booking chip */}
                <div className="mt-5 flex items-center gap-3 p-3 rounded-lg border border-amber-400/30 bg-amber-400/5">
                    <CalendarCheck size={18} weight="duotone" className="text-amber-400 shrink-0" />
                    <div className="min-w-0 flex-1">
                        <div className="text-[10px] uppercase tracking-[0.2em] text-amber-400">Booked</div>
                        <div className="text-xs text-slate-200 truncate">Tomorrow · 2:00 PM · Downtown loft tour</div>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">via cal.com</div>
                </div>
            </div>
        </div>
    );
}

function ChatLine({ role, text, delay }) {
    return (
        <div
            className={`flex ${role === "agent" ? "" : "justify-end"}`}
            style={{ animation: `float-up 0.6s ${delay}ms both` }}
        >
            <div
                className={`max-w-[85%] px-3 py-1.5 rounded-md ${
                    role === "agent"
                        ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-100"
                        : "bg-slate-800/80 border border-slate-700 text-slate-200"
                }`}
            >
                <div className="text-[8px] uppercase tracking-[0.2em] text-slate-500 mb-0.5">
                    {role === "agent" ? "AI · Ava" : "Priya"}
                </div>
                {text}
            </div>
        </div>
    );
}

/* ---------- Trust ribbon ---------- */

function TrustRibbon() {
    const items = [
        "Instant 60-Second Lead Callbacks",
        "Zero Missed Weekend Leads",
        "Auto-Book Viewings On Your Calendar",
        "Filter Out Tire-Kickers & Unqualified Buyers",
        "Seamless Sync With Your Agency CRM",
        "Instant Meta & Google Lead Ad Ingestion",
        "Human Approval For High-Ticket Buyers",
        "24/7 AI Concierge — Never Sleep On A Deal",
    ];
    return (
        <section className="border-y border-slate-800/80 bg-slate-950/50 overflow-hidden">
            <div className="marquee whitespace-nowrap py-4 flex gap-12">
                {[...items, ...items].map((it, i) => (
                    <span key={i} className="text-xs font-mono uppercase tracking-[0.2em] text-slate-400 shrink-0 flex items-center gap-3">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        {it}
                    </span>
                ))}
            </div>
        </section>
    );
}

/* ---------- Problem strip ---------- */

function ProblemStrip() {
    return (
        <section className="max-w-7xl mx-auto px-6 lg:px-10 py-24 grid md:grid-cols-3 gap-10">
            <div className="md:col-span-1">
                <div className="text-label mb-3">The 5-minute problem</div>
                <h2 className="font-serif text-4xl leading-tight">
                    Leads go cold in <span className="text-red-400 italic">under 5 minutes.</span>
                </h2>
            </div>
            <div className="md:col-span-2 grid sm:grid-cols-3 gap-4">
                <BigStat number="21×" label="likelier to close if you respond in the first 5 min" />
                <BigStat number="&lt; 27%" label="of leads ever get called back on the same day" />
                <BigStat number="60s" label="EstateX's average first response — 24/7" accent />
            </div>
        </section>
    );
}

function BigStat({ number, label, accent }) {
    return (
        <div className={`border rounded-lg p-5 ${accent ? "border-amber-400/40 bg-amber-400/5" : "border-slate-800/80 bg-slate-950/40"}`}>
            <div className={`font-serif text-4xl leading-none ${accent ? "text-amber-400" : "text-slate-100"}`}>
                {number}
            </div>
            <div className="text-xs text-slate-400 mt-3 leading-snug">{label}</div>
        </div>
    );
}

/* ---------- How it works ---------- */

function HowItWorks() {
    const steps = [
        {
            n: "01",
            icon: Phone,
            title: "Capture, everywhere.",
            body: "Public form, Google Ads Lead Form webhook, or API. Deduped by phone and dispatched to the agent in the same second.",
        },
        {
            n: "02",
            icon: Brain,
            title: "AI qualifies. Structured.",
            body: "Gemini extracts intent, budget, timeline, financing, and area, then computes a 100-point score with an explainable reasoning trail.",
        },
        {
            n: "03",
            icon: CalendarCheck,
            title: "Book, follow up, escalate.",
            body: "Hot leads are booked on your calendar automatically. Escalations wait for human approval. Everything lands on the Kanban.",
        },
    ];
    return (
        <section id="how" className="max-w-7xl mx-auto px-6 lg:px-10 py-24">
            <div className="max-w-2xl mb-14">
                <div className="text-label mb-3">How it works</div>
                <h2 className="font-serif text-4xl sm:text-5xl leading-tight">
                    A silent operator, running your book <span className="italic text-cyan-400">while you sleep.</span>
                </h2>
            </div>
            <div className="grid md:grid-cols-3 gap-6">
                {steps.map((s) => (
                    <div
                        key={s.n}
                        className="group relative border border-slate-800/80 bg-slate-950/40 rounded-lg p-7 hover:border-slate-700 transition-colors"
                    >
                        <div className="flex items-start justify-between mb-8">
                            <div className="w-11 h-11 rounded-md bg-slate-900 border border-slate-800 grid place-items-center group-hover:border-cyan-400/40 transition-colors">
                                <s.icon size={22} weight="duotone" className="text-cyan-400" />
                            </div>
                            <span className="font-mono text-[11px] text-slate-600 tracking-[0.24em]">{s.n}</span>
                        </div>
                        <h3 className="font-serif text-2xl mb-3">{s.title}</h3>
                        <p className="text-sm text-slate-400 leading-relaxed">{s.body}</p>
                    </div>
                ))}
            </div>
        </section>
    );
}

/* ---------- Agent conversation preview ---------- */

function AgentPreview() {
    return (
        <section className="relative py-24 overflow-hidden border-y border-slate-800/60 bg-gradient-to-b from-slate-950 via-slate-950/60 to-slate-950">
            <div className="absolute inset-0 grid-lines opacity-20 radial-fade" />
            <div className="relative max-w-7xl mx-auto px-6 lg:px-10 grid lg:grid-cols-12 gap-14 items-center">
                <div className="lg:col-span-5 space-y-6">
                    <div className="text-label">Voice + text</div>
                    <h2 className="font-serif text-4xl sm:text-5xl leading-tight">
                        Every conversation.
                        <br />
                        <span className="italic text-amber-400">Transcribed. Scored. Auditable.</span>
                    </h2>
                    <p className="text-slate-400 text-base leading-relaxed">
                        EstateX speaks like a top broker on their best day. Every turn is transcribed,
                        every extraction is grounded in the transcript, every score is explainable —
                        so your team can trust it and your compliance team can sleep.
                    </p>
                    <div className="grid grid-cols-2 gap-3 pt-2">
                        <SmallFeature icon={Waveform} text="Real-time transcription" />
                        <SmallFeature icon={ShieldCheck} text="Zero-hallucination extraction" />
                        <SmallFeature icon={ChartLineUp} text="0-100 rubric-based scoring" />
                        <SmallFeature icon={Sparkle} text="Adaptive tone per lead" />
                    </div>
                </div>
                <div className="lg:col-span-7">
                    <TranscriptCard />
                </div>
            </div>
        </section>
    );
}

function SmallFeature({ icon: Icon, text }) {
    return (
        <div className="flex items-center gap-2.5 text-sm text-slate-300">
            <Icon size={16} weight="duotone" className="text-cyan-400 shrink-0" />
            {text}
        </div>
    );
}

function TranscriptCard() {
    const turns = [
        { role: "agent", text: "Hi Marcus, this is Ava from EstateX Realty — do you have a minute?" },
        { role: "lead", text: "Yeah go ahead." },
        { role: "agent", text: "What kind of property are you looking for?" },
        { role: "lead", text: "Family home, ideally 4 bed. Buying, not renting." },
        { role: "agent", text: "What's your budget range?" },
        { role: "lead", text: "Around 1.2 million, cash buyer." },
        { role: "agent", text: "Timeline?" },
        { role: "lead", text: "Urgent — within 30 days." },
    ];
    return (
        <div className="relative">
            <div className="absolute -inset-6 bg-gradient-to-tr from-amber-400/10 via-transparent to-cyan-400/10 blur-3xl" />
            <div className="relative border border-slate-800/80 bg-slate-950/70 backdrop-blur-xl rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-slate-400 font-mono">
                        <Robot size={14} weight="duotone" className="text-cyan-400" />
                        Live · Vapi · en-US
                    </div>
                    <div className="text-[10px] font-mono text-emerald-400">00:47</div>
                </div>
                <div className="p-5 grid lg:grid-cols-5 gap-4">
                    <div className="lg:col-span-3 space-y-2 max-h-[340px] overflow-y-auto pr-2">
                        {turns.map((t, i) => (
                            <div
                                key={i}
                                className={`p-2.5 rounded font-mono text-xs ${
                                    t.role === "agent"
                                        ? "bg-cyan-500/5 border border-cyan-500/20 text-cyan-100"
                                        : "bg-slate-900/60 border border-slate-800 text-slate-300 ml-4"
                                }`}
                            >
                                <div className="text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-1">
                                    {t.role === "agent" ? "AI · Ava" : "Marcus"}
                                </div>
                                {t.text}
                            </div>
                        ))}
                    </div>
                    <div className="lg:col-span-2 space-y-3">
                        <div className="text-label">Extraction</div>
                        <ExtractRow label="Intent" value="buy family home" />
                        <ExtractRow label="Budget" value="$1.2M · cash" />
                        <ExtractRow label="Timeline" value="&lt; 30 days" hot />
                        <ExtractRow label="Financing" value="cash buyer" />
                        <div className="pt-3 mt-3 border-t border-slate-800 flex items-baseline justify-between">
                            <span className="text-label">Score</span>
                            <div className="text-right">
                                <div className="font-mono text-4xl text-red-400 leading-none">98</div>
                                <div className="text-[10px] uppercase tracking-[0.2em] text-red-400 mt-1">Elite · Hot</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function ExtractRow({ label, value, hot }) {
    return (
        <div className="flex items-baseline justify-between text-xs">
            <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-mono">{label}</span>
            <span className={`font-mono ${hot ? "text-amber-400" : "text-slate-200"}`}>{value}</span>
        </div>
    );
}

/* ---------- Feature grid ---------- */

function FeatureGrid() {
    const features = [
        {
            icon: Lightning,
            title: "Instant 60-second response",
            body: "Contact leads the exact moment they express interest — whether from web forms, ad campaigns, or portals.",
        },
        {
            icon: Brain,
            title: "Smart buyer qualification",
            body: "Automatically discover buyer intent, budget range, move-in timeline, financing status, and target areas.",
        },
        {
            icon: ShieldCheck,
            title: "Human control & approval",
            body: "High-value lead escalations pause for human review. Your team stays in full control of every deal.",
        },
        {
            icon: CalendarCheck,
            title: "Automated viewing booking",
            body: "Qualified buyers pick open viewing slots straight on your team's calendar without back-and-forth emails.",
        },
        {
            icon: ChartLineUp,
            title: "Real-time CRM sync",
            body: "Seamlessly push verified contacts, deal pipelines, and conversation logs straight into your CRM.",
        },
        {
            icon: Sparkle,
            title: "Localized market intelligence",
            body: "Automatically enrich lead profiles with neighborhood pricing trends, active inventory, and broker hooks.",
        },
    ];
    return (
        <section id="features" className="max-w-7xl mx-auto px-6 lg:px-10 py-24">
            <div className="max-w-2xl mb-14">
                <div className="text-label mb-3">Capabilities</div>
                <h2 className="font-serif text-4xl sm:text-5xl leading-tight">
                    Built to close deals faster, <span className="italic text-amber-400">not just chat.</span>
                </h2>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {features.map((f, i) => (
                    <div
                        key={i}
                        className="group border border-slate-800/80 bg-slate-950/40 rounded-lg p-6 hover:-translate-y-1 hover:border-slate-700 transition-all"
                    >
                        <div className="w-10 h-10 rounded-md bg-slate-900 border border-slate-800 grid place-items-center mb-4 group-hover:border-amber-400/40 transition-colors">
                            <f.icon size={20} weight="duotone" className="text-amber-400" />
                        </div>
                        <h3 className="font-serif text-xl mb-2">{f.title}</h3>
                        <p className="text-sm text-slate-400 leading-relaxed">{f.body}</p>
                    </div>
                ))}
            </div>
        </section>
    );
}

/* ---------- Architecture split ---------- */

function ArchitectureSplit() {
    return (
        <section id="architecture" className="relative py-24 border-t border-slate-800/60 bg-gradient-to-b from-slate-950 to-slate-950/70">
            <div className="max-w-7xl mx-auto px-6 lg:px-10 grid lg:grid-cols-2 gap-6">
                <ArchCard
                    tag="Automated Pipeline"
                    title="An always-on lead engine."
                    accent="amber"
                    icon={Robot}
                    bullets={[
                        "24/7 instant lead capture and multi-turn qualification",
                        "Automatic quiet-hours & opt-out management",
                        "Drip email and SMS follow-up sequences",
                        "Real-time lead scoring and pipeline status tracking",
                    ]}
                />
                <ArchCard
                    tag="AI Operations Supervisor"
                    title="An AI concierge that manages your portfolio."
                    accent="cyan"
                    icon={Brain}
                    bullets={[
                        "Continuously evaluates lead state to choose the next best action",
                        "Generates custom neighborhood briefings for buyers",
                        "Triggers human approval on high-budget luxury buyers",
                        "Full transparent event audit trail for every action taken",
                    ]}
                />
            </div>
        </section>
    );
}

function ArchCard({ tag, title, bullets, accent, icon: Icon }) {
    const accents = {
        amber: { border: "border-amber-400/30", text: "text-amber-400", glow: "shadow-[0_0_60px_-20px_rgba(251,191,36,0.4)]" },
        cyan: { border: "border-cyan-400/30", text: "text-cyan-400", glow: "shadow-[0_0_60px_-20px_rgba(34,211,238,0.4)]" },
    }[accent];
    return (
        <div className={`relative border ${accents.border} bg-slate-950/60 rounded-xl p-8 ${accents.glow}`}>
            <div className="flex items-center gap-3 mb-6">
                <div className={`w-10 h-10 rounded-md bg-slate-900 border border-slate-800 grid place-items-center`}>
                    <Icon size={20} weight="duotone" className={accents.text} />
                </div>
                <span className={`text-xs uppercase tracking-[0.24em] font-mono ${accents.text}`}>{tag}</span>
            </div>
            <h3 className="font-serif text-3xl leading-tight mb-6">{title}</h3>
            <ul className="space-y-2.5">
                {bullets.map((b) => (
                    <li key={b} className="flex items-start gap-2.5 text-sm text-slate-300">
                        <CheckCircle size={16} weight="duotone" className={`${accents.text} shrink-0 mt-0.5`} />
                        {b}
                    </li>
                ))}
            </ul>
        </div>
    );
}

/* ---------- Metrics band ---------- */

function MetricsBand() {
    return (
        <section className="max-w-7xl mx-auto px-6 lg:px-10 py-16 border-y border-slate-800/60 my-12">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
                <MetricBig value="60s" label="Median first response" />
                <MetricBig value="94%" label="Qualification agreement vs human" />
                <MetricBig value="24/7" label="Always answering" />
                <MetricBig value="3.4×" label="Booked-viewing lift" />
            </div>
        </section>
    );
}

function MetricBig({ value, label }) {
    return (
        <div>
            <div className="font-serif text-5xl sm:text-6xl text-slate-50 leading-none">{value}</div>
            <div className="text-xs text-slate-500 mt-3 uppercase tracking-[0.2em]">{label}</div>
        </div>
    );
}

/* ---------- Final CTA ---------- */

function FinalCTA({ onStartTrial }) {
    return (
        <section className="max-w-7xl mx-auto px-6 lg:px-10 py-24">
            <div
                className="relative overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/60 p-12 lg:p-20 text-center"
                style={{
                    backgroundImage:
                        "radial-gradient(ellipse at top, rgba(251,191,36,0.12), transparent 60%), radial-gradient(ellipse at bottom, rgba(34,211,238,0.08), transparent 60%)",
                }}
            >
                <div className="text-label mb-4">The moment</div>
                <h2 className="font-serif text-5xl sm:text-6xl leading-tight max-w-3xl mx-auto">
                    Every lead you don&apos;t call in 5 minutes is <span className="italic text-red-400">someone else&apos;s client.</span>
                </h2>
                <p className="text-slate-400 mt-6 max-w-xl mx-auto">
                    Deploy EstateX for your agency today — 60-second callbacks, AI buyer qualification, and instant calendar scheduling.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3 mt-8">
                    <button
                        onClick={onStartTrial}
                        data-testid="final-cta-primary"
                        className="inline-flex items-center gap-2 bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-6 py-3 rounded-md transition-colors cursor-pointer"
                    >
                        Start Agency Free Trial
                        <ArrowRight size={16} weight="bold" />
                    </button>
                    <Link
                        to="/app"
                        data-testid="final-cta-secondary"
                        className="inline-flex items-center gap-2 border border-slate-800 bg-slate-900/40 hover:bg-slate-800 text-slate-200 px-6 py-3 rounded-md"
                    >
                        View Live Command Center
                        <ArrowUpRight size={14} weight="bold" />
                    </Link>
                </div>
            </div>
        </section>
    );
}

/* ---------- Footer ---------- */

function Footer() {
    return (
        <footer className="border-t border-slate-800/80 bg-slate-950">
            <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-slate-500">
                <div className="flex items-center gap-2.5">
                    <div className="w-6 h-6 rounded bg-gradient-to-br from-amber-400 to-amber-600 grid place-items-center">
                        <House size={12} weight="fill" className="text-slate-950" />
                    </div>
                    <span className="font-serif text-sm text-slate-300">EstateX</span>
                    <span className="text-slate-600">·</span>
                    <span>© {new Date().getFullYear()} All rights reserved.</span>
                </div>
                <div className="flex items-center gap-6 font-mono uppercase tracking-[0.2em] text-[10px]">
                    <a href="#how" className="hover:text-slate-200">How</a>
                    <a href="#features" className="hover:text-slate-200">Capabilities</a>
                    <a href="#architecture" className="hover:text-slate-200">Integrations</a>
                    <Link to="/app" className="hover:text-slate-200">Agency Dashboard</Link>
                </div>
            </div>
        </footer>
    );
}

/* ---------- Agency Onboarding Modal ---------- */

function AgencyOnboardingModal({ open, onClose }) {
    const navigate = useNavigate();
    const [step, setStep] = useState(1);
    const [agency, setAgency] = useState({
        name: "",
        volume: "50-200 leads/mo",
        focus: "Residential Sales",
        source: "Facebook Lead Ads",
        crm: "HubSpot",
        calendar: "Cal.com",
    });
    const [deploying, setDeploying] = useState(false);

    if (!open) return null;

    async function handleDeploy() {
        setDeploying(true);
        try {
            await api.post("/seed");
            toast.success(`AI Concierge Deployed for ${agency.name || "your agency"}!`);
        } catch (e) {
            // Seeding is admin-only; a read-only visitor still gets the tour.
            if (e?.response?.status === 401) {
                toast.info("Read-only demo — opening the live pipeline without seeding.");
            } else {
                toast.error("Deployment failed");
                setDeploying(false);
                return;
            }
        }
        setTimeout(() => {
            onClose();
            navigate("/app");
        }, 800);
        setDeploying(false);
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
            <div className="w-full max-w-xl bg-slate-950 border border-slate-800 rounded-xl p-8 space-y-6 shadow-2xl relative">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-slate-500 hover:text-slate-200 text-sm font-mono cursor-pointer"
                >
                    ✕
                </button>

                <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.2em] text-amber-400">
                    <span>Agency Onboarding</span>
                    <span>·</span>
                    <span>Step {step} of 4</span>
                </div>

                {step === 1 && (
                    <div className="space-y-4">
                        <h2 className="font-serif text-3xl text-slate-50">Tell us about your agency</h2>
                        <p className="text-slate-400 text-sm">Configure your agency workspace to deploy AI lead concierges.</p>

                        <div className="space-y-3 pt-2">
                            <label className="block space-y-1">
                                <span className="text-xs uppercase font-mono tracking-wider text-slate-400">Agency / Brokerage Name</span>
                                <input
                                    type="text"
                                    placeholder="e.g. Apex Luxury Real Estate"
                                    value={agency.name}
                                    onChange={(e) => setAgency({ ...agency, name: e.target.value })}
                                    className="w-full bg-slate-900 border border-slate-800 rounded-md px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-amber-400"
                                />
                            </label>

                            <div className="grid grid-cols-2 gap-3">
                                <label className="block space-y-1">
                                    <span className="text-xs uppercase font-mono tracking-wider text-slate-400">Monthly Lead Volume</span>
                                    <select
                                        value={agency.volume}
                                        onChange={(e) => setAgency({ ...agency, volume: e.target.value })}
                                        className="w-full bg-slate-900 border border-slate-800 rounded-md px-3 py-2.5 text-sm text-slate-200 font-mono"
                                    >
                                        <option>1-50 leads/mo</option>
                                        <option>50-200 leads/mo</option>
                                        <option>200-1,000 leads/mo</option>
                                        <option>1,000+ leads/mo</option>
                                    </select>
                                </label>

                                <label className="block space-y-1">
                                    <span className="text-xs uppercase font-mono tracking-wider text-slate-400">Primary Focus</span>
                                    <select
                                        value={agency.focus}
                                        onChange={(e) => setAgency({ ...agency, focus: e.target.value })}
                                        className="w-full bg-slate-900 border border-slate-800 rounded-md px-3 py-2.5 text-sm text-slate-200 font-mono"
                                    >
                                        <option>Residential Sales</option>
                                        <option>Luxury Listings</option>
                                        <option>Commercial & Investment</option>
                                        <option>Rental / Property Mgmt</option>
                                    </select>
                                </label>
                            </div>
                        </div>

                        <div className="flex justify-end pt-4">
                            <Button
                                onClick={() => setStep(2)}
                                className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-5 py-2.5"
                            >
                                Lead Sources <ArrowRight size={14} weight="bold" className="ml-1" />
                            </Button>
                        </div>
                    </div>
                )}

                {step === 2 && (
                    <div className="space-y-4">
                        <h2 className="font-serif text-3xl text-slate-50">Select lead ingestion source</h2>
                        <p className="text-slate-400 text-sm">Where do your buyers and seller inquiries come from?</p>

                        <div className="grid grid-cols-2 gap-3 pt-2">
                            {[
                                { id: "Facebook Lead Ads", label: "Meta / Facebook Lead Ads", desc: "Instant form sync via Webhook" },
                                { id: "Google Search Ads", label: "Google Search Ads", desc: "Lead form extension webhook" },
                                { id: "Website Webhook", label: "Agency Website Form", desc: "Custom HTML or WordPress form" },
                                { id: "Zillow / Realtor.com", label: "Zillow / Realtor.com", desc: "Portal lead email/webhook ingestion" },
                            ].map((src) => (
                                <button
                                    key={src.id}
                                    type="button"
                                    onClick={() => setAgency({ ...agency, source: src.id })}
                                    className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${
                                        agency.source === src.id
                                            ? "border-amber-400 bg-amber-400/10 text-amber-300 shadow-lg"
                                            : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700"
                                    }`}
                                >
                                    <div className="text-xs font-mono font-semibold text-slate-200 mb-1">{src.label}</div>
                                    <div className="text-[11px] text-slate-400">{src.desc}</div>
                                </button>
                            ))}
                        </div>

                        <div className="flex justify-between pt-4">
                            <Button variant="outline" onClick={() => setStep(1)} className="border-slate-800 text-slate-400">
                                Back
                            </Button>
                            <Button
                                onClick={() => setStep(3)}
                                className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-5 py-2.5"
                            >
                                Connect CRM & Calendar <ArrowRight size={14} weight="bold" className="ml-1" />
                            </Button>
                        </div>
                    </div>
                )}

                {step === 3 && (
                    <div className="space-y-4">
                        <h2 className="font-serif text-3xl text-slate-50">Connect agency tools</h2>
                        <p className="text-slate-400 text-sm">Select where your leads and calendar viewings should sync.</p>

                        <div className="space-y-4 pt-2">
                            <div>
                                <span className="text-xs uppercase font-mono tracking-wider text-slate-400 block mb-2">Select Agency CRM</span>
                                <div className="grid grid-cols-3 gap-2">
                                    {["HubSpot", "Salesforce", "Follow Up Boss"].map((c) => (
                                        <button
                                            key={c}
                                            type="button"
                                            onClick={() => setAgency({ ...agency, crm: c })}
                                            className={`p-3 rounded-lg border text-xs font-mono transition-all cursor-pointer ${
                                                agency.crm === c
                                                    ? "border-amber-400 bg-amber-400/10 text-amber-300 font-semibold"
                                                    : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700"
                                            }`}
                                        >
                                            {c}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div>
                                <span className="text-xs uppercase font-mono tracking-wider text-slate-400 block mb-2">Select Booking Calendar</span>
                                <div className="grid grid-cols-3 gap-2">
                                    {["Cal.com", "Google Calendar", "Outlook"].map((cal) => (
                                        <button
                                            key={cal}
                                            type="button"
                                            onClick={() => setAgency({ ...agency, calendar: cal })}
                                            className={`p-3 rounded-lg border text-xs font-mono transition-all cursor-pointer ${
                                                agency.calendar === cal
                                                    ? "border-cyan-400 bg-cyan-400/10 text-cyan-300 font-semibold"
                                                    : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700"
                                            }`}
                                        >
                                            {cal}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="flex justify-between pt-4">
                            <Button variant="outline" onClick={() => setStep(2)} className="border-slate-800 text-slate-400">
                                Back
                            </Button>
                            <Button
                                onClick={() => setStep(4)}
                                className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-5 py-2.5"
                            >
                                Review & Deploy <ArrowRight size={14} weight="bold" className="ml-1" />
                            </Button>
                        </div>
                    </div>
                )}

                {step === 4 && (
                    <div className="space-y-4">
                        <h2 className="font-serif text-3xl text-slate-50">Ready to launch AI Concierge</h2>
                        <p className="text-slate-400 text-sm">Review your agency setup and deploy live AI lead qualification.</p>

                        <div className="border border-slate-800 bg-slate-900/60 rounded-lg p-4 space-y-2 text-xs font-mono">
                            <div className="flex justify-between text-slate-300">
                                <span className="text-slate-500">AGENCY:</span>
                                <span>{agency.name || "Apex Real Estate"}</span>
                            </div>
                            <div className="flex justify-between text-slate-300">
                                <span className="text-slate-500">VOLUME:</span>
                                <span>{agency.volume}</span>
                            </div>
                            <div className="flex justify-between text-slate-300">
                                <span className="text-slate-500">LEAD SOURCE:</span>
                                <span className="text-emerald-400">{agency.source}</span>
                            </div>
                            <div className="flex justify-between text-slate-300">
                                <span className="text-slate-500">CRM SYNC:</span>
                                <span className="text-amber-400">{agency.crm}</span>
                            </div>
                            <div className="flex justify-between text-slate-300">
                                <span className="text-slate-500">CALENDAR:</span>
                                <span className="text-cyan-400">{agency.calendar}</span>
                            </div>
                        </div>

                        <div className="flex justify-between pt-4">
                            <Button variant="outline" onClick={() => setStep(3)} className="border-slate-800 text-slate-400">
                                Back
                            </Button>
                            <Button
                                onClick={handleDeploy}
                                disabled={deploying}
                                className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold px-6 py-2.5"
                            >
                                {deploying ? "Deploying Agency Concierge…" : "Deploy AI Concierge Live"}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
