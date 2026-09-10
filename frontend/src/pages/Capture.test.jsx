import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Capture from "./Capture";
import { api } from "../lib/api";

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
            post: jest.fn(),
        },
    };
});

describe("Capture component", () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    test("renders lead capture form fields", () => {
        render(<Capture />);

        expect(screen.getByTestId("capture-page")).toBeInTheDocument();
        expect(screen.getByTestId("capture-form")).toBeInTheDocument();
        expect(screen.getByTestId("input-name")).toBeInTheDocument();
        expect(screen.getByTestId("input-phone")).toBeInTheDocument();
        expect(screen.getByTestId("input-email")).toBeInTheDocument();
        expect(screen.getByTestId("btn-submit-lead")).toBeInTheDocument();
    });

    test("submitting without required fields does not call api.post", () => {
        render(<Capture />);

        fireEvent.click(screen.getByTestId("btn-submit-lead"));
        expect(api.post).not.toHaveBeenCalled();
    });

    test("submitting valid details dispatches lead creation", async () => {
        api.post.mockResolvedValueOnce({ data: { id: "lead-new-123" } });
        render(<Capture />);

        await userEvent.type(screen.getByTestId("input-name"), "Samantha Wells");
        await userEvent.type(screen.getByTestId("input-phone"), "+15551234567");
        await userEvent.type(screen.getByTestId("input-email"), "samantha@example.com");

        fireEvent.click(screen.getByTestId("btn-submit-lead"));

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/lead", {
                name: "Samantha Wells",
                phone: "+15551234567",
                email: "samantha@example.com",
                source: "web",
            });
        });
    });

    test("navigates to dashboard when clicking pipeline button", () => {
        render(<Capture />);

        const gotoBtn = screen.getByTestId("btn-goto-dashboard");
        fireEvent.click(gotoBtn);
        expect(mockNavigate).toHaveBeenCalledWith("/app");
    });
});
