import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API,
    headers: { "Content-Type": "application/json" },
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
