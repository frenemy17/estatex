import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import NotFound from "./NotFound";

describe("NotFound Component", () => {
    test("renders 404 message and return buttons", () => {
        render(
            <MemoryRouter>
                <NotFound />
            </MemoryRouter>
        );

        expect(screen.getByTestId("not-found-page")).toBeInTheDocument();
        expect(screen.getByText("Error 404")).toBeInTheDocument();
        expect(screen.getByText("Property or Page Not Found")).toBeInTheDocument();
        expect(screen.getByText(/Return to Pipeline/i)).toBeInTheDocument();
        expect(screen.getByText(/Public Landing/i)).toBeInTheDocument();
    });
});
