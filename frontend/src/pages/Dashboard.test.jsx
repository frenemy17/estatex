import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";
import { api, setAdminToken } from "../lib/api";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
    ...jest.requireActual("react-router-dom"),
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

// Mock usePoll to run the fetch once upon mount
jest.mock("../lib/usePoll", () => ({
    usePoll: (fn) => {
        const { useEffect } = require("react");
        useEffect(() => {
            fn();
        }, []);
    },
}));

// Mock ProviderStatus component
jest.mock("../components/ProviderStatus", () => () => <div data-testid="mock-provider-status" />);

const sampleLeads = [
    {
        id: "lead-1",
        name: "Alice Johnson",
        phone: "+15550001",
        email: "alice@example.com",
        status: "NEW",
        score: 50,
        qualification: { area: "Downtown", intent: "Buying" },
    },
    {
        id: "lead-2",
        name: "Bob Smith",
        phone: "+15550002",
        email: "bob@example.com",
        status: "CALLING",
        score: 75,
        qualification: { area: "Suburbs" },
    },
    {
        id: "lead-3",
        name: "Charlie Brown",
        phone: "+15550003",
        email: "charlie@example.com",
        status: "HOT",
        score: 95,
        qualification: { area: "Metro" },
    },
    {
        id: "lead-4",
        name: "David Miller",
        phone: "+15550004",
        email: "david@example.com",
        status: "BOOKED",
        score: 88,
        qualification: { area: "Downtown" },
    },
    {
        id: "lead-5",
        name: "Eva Davis",
        phone: "+15550005",
        email: "eva@example.com",
        status: "QUALIFIED",
        score: 72,
        pending_approval: true,
        qualification: { area: "Uptown" },
    },
];

describe("Dashboard component and Kanban Pipeline", () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
        api.get.mockResolvedValue({ data: sampleLeads });
    });

    test("renders Kanban board with all 7 canonical status columns", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            expect(screen.getByTestId("kanban-board")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-new")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-calling")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-in_conversation")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-qualified")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-hot")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-nurture")).toBeInTheDocument();
            expect(screen.getByTestId("kanban-column-booked")).toBeInTheDocument();
        });
    });

    test("distributes lead cards into the correct status columns", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            const newCol = screen.getByTestId("kanban-column-new");
            const callingCol = screen.getByTestId("kanban-column-calling");
            const hotCol = screen.getByTestId("kanban-column-hot");
            const bookedCol = screen.getByTestId("kanban-column-booked");
            const qualifiedCol = screen.getByTestId("kanban-column-qualified");

            expect(newCol).toHaveTextContent("Alice Johnson");
            expect(callingCol).toHaveTextContent("Bob Smith");
            expect(hotCol).toHaveTextContent("Charlie Brown");
            expect(bookedCol).toHaveTextContent("David Miller");
            expect(qualifiedCol).toHaveTextContent("Eva Davis");
        });
    });

    test("calculates and displays KPI summaries accurately", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            // inFlight = 1 (Bob Smith in CALLING)
            expect(screen.getByTestId("kpi-inflight")).toHaveTextContent("1");
            // totalHot = 2 (Charlie Brown has status HOT, David Miller has score 88 >= 85)
            expect(screen.getByTestId("kpi-hot")).toHaveTextContent("2");
            // totalBooked = 1 (David Miller)
            expect(screen.getByTestId("kpi-booked")).toHaveTextContent("1");
            // conversionRate = Math.round(((totalBooked + totalHot) / 5) * 100) = (3 / 5) * 100 = 60%
            expect(screen.getByTestId("kpi-conversion")).toHaveTextContent("60%");
        });
    });

    test("filters leads by search query matching name or area", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            expect(screen.getByTestId("lead-card-lead-1")).toBeInTheDocument();
        });

        const searchInput = screen.getByPlaceholderText("Search leads, phones, locations...");
        await userEvent.type(searchInput, "Alice");

        expect(screen.getByTestId("lead-card-lead-1")).toBeInTheDocument();
        expect(screen.queryByTestId("lead-card-lead-2")).not.toBeInTheDocument();
        expect(screen.queryByTestId("lead-card-lead-3")).not.toBeInTheDocument();

        await userEvent.clear(searchInput);
        await userEvent.type(searchInput, "Downtown");

        expect(screen.getByTestId("lead-card-lead-1")).toBeInTheDocument(); // Downtown
        expect(screen.getByTestId("lead-card-lead-4")).toBeInTheDocument(); // Downtown
        expect(screen.queryByTestId("lead-card-lead-2")).not.toBeInTheDocument();
    });

    test("filters leads using category pill buttons", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            expect(screen.getByTestId("lead-card-lead-1")).toBeInTheDocument();
        });

        // Click "In Flight"
        fireEvent.click(screen.getByText(/In Flight \(/i));
        expect(screen.getByTestId("lead-card-lead-2")).toBeInTheDocument();
        expect(screen.queryByTestId("lead-card-lead-1")).not.toBeInTheDocument();

        // Click "Booked"
        fireEvent.click(screen.getByText(/Booked \(/i));
        expect(screen.getByTestId("lead-card-lead-4")).toBeInTheDocument();
        expect(screen.queryByTestId("lead-card-lead-2")).not.toBeInTheDocument();

        // Click "Approval Pending"
        fireEvent.click(screen.getByText(/Approval Pending \(/i));
        expect(screen.getByTestId("lead-card-lead-5")).toBeInTheDocument();
        expect(screen.queryByTestId("lead-card-lead-4")).not.toBeInTheDocument();
    });

    test("clicking a lead card navigates to lead detail view", async () => {
        render(<Dashboard />);

        await waitFor(() => {
            expect(screen.getByTestId("lead-card-lead-1")).toBeInTheDocument();
        });

        fireEvent.click(screen.getByTestId("lead-card-lead-1"));
        expect(mockNavigate).toHaveBeenCalledWith("/leads/lead-1");
    });

    test("triggers seeding when admin token is present and seed button is clicked", async () => {
        setAdminToken("active-admin-key");
        api.post.mockResolvedValueOnce({ data: { created: 15 } });

        render(<Dashboard />);

        const seedButton = await screen.findByText("Seed 15 Leads");
        expect(seedButton).toBeEnabled();

        fireEvent.click(seedButton);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/seed");
        });
    });
});
