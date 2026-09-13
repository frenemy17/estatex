import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import LeadDetail from "./LeadDetail";
import { api } from "../lib/api";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
    ...jest.requireActual("react-router-dom"),
    useParams: () => ({ id: "lead-456" }),
    useNavigate: () => mockNavigate,
}));

jest.mock("../lib/api", () => {
    const actual = jest.requireActual("../lib/api");
    return {
        ...actual,
        api: {
            ...actual.api,
            get: jest.fn(),
            post: jest.fn(),
        },
    };
});

const sampleLead = {
    id: "lead-456",
    name: "Marcus Vance",
    phone: "+14155552671",
    email: "marcus@example.com",
    status: "QUALIFIED",
    score: 82,
    updated_at: "2026-09-10T12:00:00Z",
    pending_approval: true,
    qualification: {
        intent: "Luxury Buyer",
        budget: "$2.5M",
        timeline: "Immediate",
        financing: "Pre-approved",
        area: "Pacific Heights",
    },
};

describe("LeadDetail component", () => {
    beforeEach(() => {
        jest.clearAllMocks();
        api.get.mockImplementation((url) => {
            if (url === "/leads/lead-456") return Promise.resolve({ data: sampleLead });
            if (url === "/leads/lead-456/events") return Promise.resolve({ data: [] });
            if (url === "/leads/lead-456/call-logs") return Promise.resolve({ data: [] });
            if (url === "/leads/lead-456/appointments") return Promise.resolve({ data: [] });
            if (url === "/leads/lead-456/slots") return Promise.resolve({ data: { slots: [] } });
            return Promise.resolve({ data: {} });
        });
    });

    test("renders lead information and qualification breakdown", async () => {
        render(<LeadDetail />);

        await waitFor(() => {
            expect(screen.getByTestId("lead-detail")).toBeInTheDocument();
            expect(screen.getByText("Marcus Vance")).toBeInTheDocument();
            expect(screen.getByText("+14155552671")).toBeInTheDocument();
            expect(screen.getByText("marcus@example.com")).toBeInTheDocument();
            expect(screen.getByText("82")).toBeInTheDocument();
            expect(screen.getByText("Luxury Buyer")).toBeInTheDocument();
            expect(screen.getByText("$2.5M")).toBeInTheDocument();
            expect(screen.getByText("Pacific Heights")).toBeInTheDocument();
        });
    });

    test("renders escalation banner and handles approve action", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<LeadDetail />);

        const banner = await screen.findByTestId("approval-banner");
        expect(banner).toBeInTheDocument();
        expect(screen.getByText(/escalate this lead to a senior agent/i)).toBeInTheDocument();

        const approveBtn = screen.getByTestId("btn-approve-escalation");
        fireEvent.click(approveBtn);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/leads/lead-456/approve");
        });
    });

    test("handles escalation reject action", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<LeadDetail />);

        const rejectBtn = await screen.findByTestId("btn-reject-escalation");
        fireEvent.click(rejectBtn);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/leads/lead-456/reject");
        });
    });

    test("triggers supervisor execution when btn-run-supervisor is clicked", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<LeadDetail />);

        const supervisorBtn = await screen.findByTestId("btn-run-supervisor");
        fireEvent.click(supervisorBtn);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/leads/lead-456/supervisor");
        });
    });

    test("triggers pipeline rerun when btn-rerun is clicked", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<LeadDetail />);

        const rerunBtn = await screen.findByTestId("btn-rerun");
        fireEvent.click(rerunBtn);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/leads/lead-456/rerun");
        });
    });

    test("triggers opt-out when btn-opt-out is clicked", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<LeadDetail />);

        const optOutBtn = await screen.findByTestId("btn-opt-out");
        fireEvent.click(optOutBtn);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/leads/lead-456/opt-out");
        });
    });
});
