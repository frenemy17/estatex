import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";
import { api, getAuthToken, getAuthUser } from "../lib/api";

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

describe("Login Component", () => {
    beforeEach(() => {
        localStorage.clear();
        jest.clearAllMocks();
    });

    test("renders login form elements and 1-click demo button", () => {
        render(
            <MemoryRouter>
                <Login />
            </MemoryRouter>
        );

        expect(screen.getByTestId("login-page")).toBeInTheDocument();
        expect(screen.getByTestId("btn-demo-fill")).toBeInTheDocument();
        expect(screen.getByTestId("tab-sign-in")).toBeInTheDocument();
        expect(screen.getByTestId("tab-register")).toBeInTheDocument();
        expect(screen.getByTestId("input-email")).toBeInTheDocument();
        expect(screen.getByTestId("input-password")).toBeInTheDocument();
        expect(screen.getByTestId("btn-auth-submit")).toBeInTheDocument();
    });

    test("switches between sign in and register tabs", async () => {
        render(
            <MemoryRouter>
                <Login />
            </MemoryRouter>
        );

        expect(screen.queryByTestId("input-name")).not.toBeInTheDocument();

        fireEvent.click(screen.getByTestId("tab-register"));
        expect(screen.getByTestId("input-name")).toBeInTheDocument();
        expect(screen.getByText("Create Concierge Access")).toBeInTheDocument();

        fireEvent.click(screen.getByTestId("tab-sign-in"));
        expect(screen.queryByTestId("input-name")).not.toBeInTheDocument();
        expect(screen.getByText("Agency Portal Sign In")).toBeInTheDocument();
    });

    test("clicking demo fill prefills demo email and password", () => {
        render(
            <MemoryRouter>
                <Login />
            </MemoryRouter>
        );

        const emailInput = screen.getByTestId("input-email");
        const passwordInput = screen.getByTestId("input-password");

        fireEvent.click(screen.getByTestId("btn-demo-fill"));

        expect(emailInput.value).toBe("agent@estatex.io");
        expect(passwordInput.value).toBe("estatex2026");
    });

    test("submits login successfully and saves auth session", async () => {
        api.post.mockResolvedValueOnce({
            data: {
                access_token: "mock-jwt-token-12345",
                token_type: "bearer",
                user: {
                    id: "user-1",
                    email: "agent@estatex.io",
                    name: "Alex Vance",
                    role: "agent",
                },
            },
        });

        render(
            <MemoryRouter>
                <Login />
            </MemoryRouter>
        );

        fireEvent.click(screen.getByTestId("btn-demo-fill"));
        fireEvent.click(screen.getByTestId("btn-auth-submit"));

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/auth/login", {
                email: "agent@estatex.io",
                password: "estatex2026",
            });
            expect(getAuthToken()).toBe("mock-jwt-token-12345");
            expect(getAuthUser()).toEqual({
                id: "user-1",
                email: "agent@estatex.io",
                name: "Alex Vance",
                role: "agent",
            });
            expect(mockNavigate).toHaveBeenCalledWith("/app", { replace: true });
        });
    });

    test("registers a new agent account successfully", async () => {
        api.post.mockResolvedValueOnce({
            data: {
                access_token: "new-user-jwt",
                token_type: "bearer",
                user: {
                    id: "user-new",
                    email: "newagent@estatex.io",
                    name: "Sarah Broker",
                    role: "agent",
                },
            },
        });

        render(
            <MemoryRouter>
                <Login />
            </MemoryRouter>
        );

        fireEvent.click(screen.getByTestId("tab-register"));

        await userEvent.type(screen.getByTestId("input-name"), "Sarah Broker");
        await userEvent.type(screen.getByTestId("input-email"), "newagent@estatex.io");
        await userEvent.type(screen.getByTestId("input-password"), "secretpass123");

        fireEvent.click(screen.getByTestId("btn-auth-submit"));

        await waitFor(() => {
            expect(api.post).toHaveBeenCalledWith("/auth/register", {
                name: "Sarah Broker",
                email: "newagent@estatex.io",
                password: "secretpass123",
                role: "agent",
            });
            expect(getAuthToken()).toBe("new-user-jwt");
        });
    });
});
