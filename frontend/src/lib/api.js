import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = BACKEND_URL ? (BACKEND_URL.endsWith("/api") ? BACKEND_URL : `${BACKEND_URL}/api`) : "/api";

export const api = axios.create({
    baseURL: API,
    headers: { "Content-Type": "application/json" },
});

/* ---------- Admin token ----------
 * Write routes (seed / reset / bulk / simulate / tick) require X-Admin-Token.
 * Without one the app is a read-only demo: browsing works, writing is disabled
 * in the UI instead of failing with a 401 the visitor can't explain.
 */

const ADMIN_KEY = "estatex_admin_token";
const ADMIN_EVENT = "estatex:admin-token";

export function getAdminToken() {
    try {
        return localStorage.getItem(ADMIN_KEY) || "";
    } catch {
        return ""; // private mode / storage disabled
    }
}

export function setAdminToken(token) {
    try {
        if (token) localStorage.setItem(ADMIN_KEY, token);
        else localStorage.removeItem(ADMIN_KEY);
    } catch {
        /* ignore */
    }
    window.dispatchEvent(new Event(ADMIN_EVENT));
}

export function onAdminTokenChange(handler) {
    window.addEventListener(ADMIN_EVENT, handler);
    return () => window.removeEventListener(ADMIN_EVENT, handler);
}

const AUTH_KEY = "estatex_auth_token";
const USER_KEY = "estatex_auth_user";
const AUTH_EVENT = "estatex:auth-change";

export function getAuthToken() {
    try {
        return localStorage.getItem(AUTH_KEY) || "";
    } catch {
        return "";
    }
}

export function getAuthUser() {
    try {
        const raw = localStorage.getItem(USER_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

export function setAuthSession(token, user) {
    try {
        if (token) {
            localStorage.setItem(AUTH_KEY, token);
            if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
        } else {
            localStorage.removeItem(AUTH_KEY);
            localStorage.removeItem(USER_KEY);
        }
    } catch {
        /* ignore */
    }
    window.dispatchEvent(new Event(AUTH_EVENT));
}

export function clearAuthSession() {
    setAuthSession(null, null);
}

export function onAuthChange(handler) {
    window.addEventListener(AUTH_EVENT, handler);
    return () => window.removeEventListener(AUTH_EVENT, handler);
}

api.interceptors.request.use((config) => {
    const adminToken = getAdminToken();
    if (adminToken) config.headers["X-Admin-Token"] = adminToken;
    const authToken = getAuthToken();
    if (authToken) config.headers["Authorization"] = `Bearer ${authToken}`;
    return config;
});

export const STATUSES = [
    "NEW",
    "CALLING",
    "IN_CONVERSATION",
    "QUALIFIED",
    "HOT",
    "NURTURE",
    "BOOKED",
];

export const STATUS_META = {
    NEW: { color: "#60a5fa", label: "New", dot: "bg-blue-400" },
    CALLING: { color: "#22d3ee", label: "Calling", dot: "bg-cyan-400 animate-pulse-dot" },
    IN_CONVERSATION: { color: "#818cf8", label: "In Conversation", dot: "bg-indigo-400 animate-pulse-dot" },
    QUALIFIED: { color: "#34d399", label: "Qualified", dot: "bg-emerald-400" },
    HOT: { color: "#ef4444", label: "Hot", dot: "bg-red-500" },
    NURTURE: { color: "#fbbf24", label: "Nurture", dot: "bg-amber-400" },
    BOOKED: { color: "#d946ef", label: "Booked", dot: "bg-fuchsia-500" },
};

export function scoreBand(score) {
    if (score >= 85) return { label: "Elite", color: "#ef4444" };
    if (score >= 70) return { label: "Qualified", color: "#34d399" };
    if (score >= 40) return { label: "Nurture", color: "#fbbf24" };
    return { label: "Cold", color: "#64748b" };
}

/* ---------- Provider chips ----------
 * Mirrors GET /api/providers. Grey = mocked (no keys), green = live and the last
 * real call succeeded, amber = live but the provider is returning errors.
 */

export const PROVIDER_TONES = {
    LIVE_OK: { color: "#34d399", label: "Live", dot: "bg-emerald-400" },
    LIVE_ERROR: { color: "#ef4444", label: "Failed", dot: "bg-red-500 animate-pulse-dot" },
    MOCK: { color: "#eab308", label: "Mock", dot: "bg-yellow-500" },
};

export function providerTone(p) {
    if (p.mode !== "LIVE") return PROVIDER_TONES.MOCK;
    return p.last_ok === false ? PROVIDER_TONES.LIVE_ERROR : PROVIDER_TONES.LIVE_OK;
}

/** Human-readable "why is this chip that colour" text for the hover title. */
export function providerHint(p) {
    const lines = [p.capability];
    if (p.mode === "LIVE") {
        if (p.last_ok === false) {
            lines.push(`Last call failed${p.last_status ? ` — HTTP ${p.last_status}` : ""}`);
            if (p.last_error) lines.push(p.last_error);
        } else if (p.last_ok === true) {
            lines.push("Last call OK");
        } else {
            lines.push("Configured — no calls yet");
        }
        if (p.calls) lines.push(`${p.calls} calls · ${p.failures || 0} failures`);
    } else if (p.missing_env?.length) {
        lines.push(`Mocked — set ${p.missing_env.join(", ")}`);
    } else if (p.gate && !p.gate_open) {
        lines.push(`Keys present — set ${p.gate}=1 to go live`);
    } else {
        lines.push("Mocked — DEMO_MODE is on");
    }
    return lines.join("\n");
}

/** Audit-log events that represent a failure and should render red. */
export function isErrorEvent(e) {
    return e.kind === "error" || /error|failed|timeout|blocked|rejected|unavailable/i.test(e.reason || "");
}
