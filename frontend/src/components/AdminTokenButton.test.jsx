import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminTokenButton from "./AdminTokenButton";
import { api, getAdminToken, setAdminToken } from "../lib/api";

// Mock the API module
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

describe("AdminTokenButton component", () => {
    beforeEach(() => {
        localStorage.clear();
        setAdminToken("");
        jest.clearAllMocks();
    });

    test("renders in read-only mode by default", () => {
        render(<AdminTokenButton />);
        const button = screen.getByTestId("btn-admin-token");
        expect(button).toBeInTheDocument();
        expect(button).toHaveTextContent("Read-only");
    });

    test("opens unlock modal on click when in read-only mode", async () => {
        render(<AdminTokenButton />);
        const button = screen.getByTestId("btn-admin-token");
        fireEvent.click(button);

        expect(screen.getByText("Unlock write actions")).toBeInTheDocument();
        expect(screen.getByTestId("input-admin-token")).toBeInTheDocument();
        expect(screen.getByTestId("btn-save-admin-token")).toBeInTheDocument();
    });

    test("closes modal when clicking cancel or close button", async () => {
        render(<AdminTokenButton />);
        fireEvent.click(screen.getByTestId("btn-admin-token"));
        expect(screen.getByText("Unlock write actions")).toBeInTheDocument();

        fireEvent.click(screen.getByText("Cancel"));
        expect(screen.queryByText("Unlock write actions")).not.toBeInTheDocument();
    });

    test("saves valid token, verifies via api.post('/tick'), and transitions to Admin mode", async () => {
        api.post.mockResolvedValueOnce({ data: { ok: true } });
        render(<AdminTokenButton />);

        fireEvent.click(screen.getByTestId("btn-admin-token"));
        const input = screen.getByTestId("input-admin-token");
        await userEvent.type(input, "super-secret-admin");

        const saveButton = screen.getByTestId("btn-save-admin-token");
        fireEvent.click(saveButton);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/tick");
            expect(getAdminToken()).toBe("super-secret-admin");
            expect(screen.getByTestId("btn-admin-token")).toHaveTextContent("Admin");
        });
    });

    test("rejects token when /tick returns 401 unauthorized", async () => {
        api.post.mockRejectedValueOnce({ response: { status: 401 } });
        render(<AdminTokenButton />);

        fireEvent.click(screen.getByTestId("btn-admin-token"));
        const input = screen.getByTestId("input-admin-token");
        await userEvent.type(input, "wrong-token");

        fireEvent.click(screen.getByTestId("btn-save-admin-token"));

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/tick");
            expect(getAdminToken()).toBe("");
            expect(screen.getByTestId("btn-admin-token")).toHaveTextContent("Read-only");
        });
    });

    test("clicking Admin button clears token and reverts to Read-only", async () => {
        setAdminToken("existing-admin-token");
        render(<AdminTokenButton />);

        const button = screen.getByTestId("btn-admin-token");
        expect(button).toHaveTextContent("Admin");

        fireEvent.click(button);
        await waitFor(() => {
            expect(getAdminToken()).toBe("");
            expect(button).toHaveTextContent("Read-only");
        });
    });
});
