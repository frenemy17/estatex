import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import ServerWakeBanner from "./ServerWakeBanner";

jest.mock("../lib/api", () => {
    const actual = jest.requireActual("../lib/api");
    return {
        ...actual,
        warmupBackend: jest.fn(),
    };
});

describe("ServerWakeBanner component", () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        act(() => {
            jest.runOnlyPendingTimers();
        });
        jest.useRealTimers();
    });

    test("remains hidden when server is warm / idle", () => {
        render(<ServerWakeBanner />);
        expect(screen.queryByTestId("server-wake-banner")).not.toBeInTheDocument();
    });

    test("renders waking banner and increments elapsed timer during cold start", () => {
        render(<ServerWakeBanner />);

        act(() => {
            window.dispatchEvent(
                new CustomEvent("estatex:server-status", {
                    detail: { status: "waking" },
                })
            );
        });

        expect(screen.getByTestId("server-wake-banner")).toBeInTheDocument();
        expect(screen.getByText(/Waking up cloud server/i)).toBeInTheDocument();
        expect(screen.getByText(/Render Cloud Boot/i)).toBeInTheDocument();
        expect(screen.getByText(/0s elapsed/i)).toBeInTheDocument();

        // Advance 3 seconds
        act(() => {
            jest.advanceTimersByTime(3000);
        });

        expect(screen.getByText(/3s elapsed/i)).toBeInTheDocument();
    });

    test("dismiss button hides the banner immediately", () => {
        render(<ServerWakeBanner />);

        act(() => {
            window.dispatchEvent(
                new CustomEvent("estatex:server-status", {
                    detail: { status: "waking" },
                })
            );
        });

        expect(screen.getByTestId("server-wake-banner")).toBeInTheDocument();

        const dismissBtn = screen.getByTitle("Dismiss");
        fireEvent.click(dismissBtn);

        expect(screen.queryByTestId("server-wake-banner")).not.toBeInTheDocument();
    });

    test("switches to connected state when awake event is received", () => {
        render(<ServerWakeBanner />);

        act(() => {
            window.dispatchEvent(
                new CustomEvent("estatex:server-status", {
                    detail: { status: "waking" },
                })
            );
        });

        expect(screen.getByText(/Waking up cloud server/i)).toBeInTheDocument();

        act(() => {
            window.dispatchEvent(
                new CustomEvent("estatex:server-status", {
                    detail: { status: "awake" },
                })
            );
        });

        expect(screen.getByText(/Cloud server is online and active!/i)).toBeInTheDocument();
        expect(screen.getByText("✓ Connected")).toBeInTheDocument();

        // Auto-dismisses after 2.8s
        act(() => {
            jest.advanceTimersByTime(3000);
        });

        expect(screen.queryByTestId("server-wake-banner")).not.toBeInTheDocument();
    });
});
