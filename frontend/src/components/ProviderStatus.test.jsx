import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import ProviderStatus from "./ProviderStatus";
import { api } from "../lib/api";

jest.mock("../lib/api", () => {
    const actual = jest.requireActual("../lib/api");
    return {
        ...actual,
        api: {
            ...actual.api,
            get: jest.fn(),
        },
    };
});

// Mock usePoll to run in useEffect so state updates trigger cleanly
jest.mock("../lib/usePoll", () => ({
    usePoll: (fn) => {
        const { useEffect } = require("react");
        useEffect(() => {
            fn();
        }, []);
    },
}));

describe("ProviderStatus component", () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    test("returns null when no provider data is available", async () => {
        api.get.mockResolvedValue({ data: { providers: [] } });
        const { container } = render(<ProviderStatus />);
        await waitFor(() => {
            expect(api.get).toHaveBeenCalledWith("/providers");
        });
        expect(container.firstChild).toBeNull();
    });

    test("renders all integration chips in demo mode", async () => {
        const mockPayload = {
            demo_mode: true,
            providers: [
                { name: "groq", label: "Groq", capability: "LLM", mode: "MOCK" },
                { name: "cal", label: "Cal.com", capability: "Booking", mode: "MOCK" },
                { name: "resend", label: "Resend", capability: "Email", mode: "MOCK" },
                { name: "twilio_voice", label: "Twilio Voice", capability: "Calling", mode: "MOCK" },
                { name: "twilio_sms", label: "Twilio SMS", capability: "SMS", mode: "MOCK" },
                { name: "hubspot", label: "HubSpot", capability: "CRM", mode: "MOCK" },
            ],
        };

        api.get.mockResolvedValue({ data: mockPayload });
        render(<ProviderStatus />);

        await waitFor(() => {
            expect(screen.getByTestId("provider-status")).toBeInTheDocument();
            expect(screen.getByText("DEMO_MODE — every provider mocked")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-groq")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-cal")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-resend")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-twilio_voice")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-twilio_sms")).toBeInTheDocument();
            expect(screen.getByTestId("provider-chip-hubspot")).toBeInTheDocument();
        });
    });

    test("renders live chips with green status when mode is LIVE", async () => {
        const livePayload = {
            demo_mode: false,
            providers: [
                { name: "groq", label: "Groq", capability: "LLM", mode: "LIVE", last_ok: true },
                { name: "resend", label: "Resend", capability: "Email", mode: "LIVE", last_ok: true },
                { name: "cal", label: "Cal.com", capability: "Booking", mode: "MOCK" },
            ],
        };

        api.get.mockResolvedValue({ data: livePayload });
        render(<ProviderStatus />);

        await waitFor(() => {
            expect(screen.getByText("2/3 live")).toBeInTheDocument();
            const groqChip = screen.getByTestId("provider-chip-groq");
            expect(groqChip).toHaveTextContent("Groq");
            expect(groqChip).toHaveTextContent("Live");

            const calChip = screen.getByTestId("provider-chip-cal");
            expect(calChip).toHaveTextContent("Cal.com");
            expect(calChip).toHaveTextContent("Mock");
        });
    });
});
