import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";
import { setAuthSession, clearAuthSession } from "../lib/api";

describe("ProtectedRoute Component", () => {
    beforeEach(() => {
        clearAuthSession();
    });

    test("redirects unauthenticated visitor to /login", () => {
        render(
            <MemoryRouter initialEntries={["/app"]}>
                <Routes>
                    <Route path="/login" element={<div>Login Page Mock</div>} />
                    <Route
                        path="/app"
                        element={
                            <ProtectedRoute>
                                <div>Protected Content</div>
                            </ProtectedRoute>
                        }
                    />
                </Routes>
            </MemoryRouter>
        );

        expect(screen.getByText("Login Page Mock")).toBeInTheDocument();
        expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });

    test("allows authenticated user through to protected content", () => {
        setAuthSession("valid-test-token", { name: "Agent Alex" });

        render(
            <MemoryRouter initialEntries={["/app"]}>
                <Routes>
                    <Route path="/login" element={<div>Login Page Mock</div>} />
                    <Route
                        path="/app"
                        element={
                            <ProtectedRoute>
                                <div>Protected Content</div>
                            </ProtectedRoute>
                        }
                    />
                </Routes>
            </MemoryRouter>
        );

        expect(screen.getByText("Protected Content")).toBeInTheDocument();
        expect(screen.queryByText("Login Page Mock")).not.toBeInTheDocument();
    });
});
