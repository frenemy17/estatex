import { cn } from "./utils";

describe("cn utility function", () => {
    test("combines standard class names", () => {
        expect(cn("px-4", "py-2")).toBe("px-4 py-2");
    });

    test("resolves conflicting tailwind classes with twMerge", () => {
        expect(cn("px-2", "px-4")).toBe("px-4");
        expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
    });

    test("handles conditionals and falsy values", () => {
        expect(cn("btn", false && "btn-hidden", null, undefined, 0 && "zero", "active")).toBe("btn active");
    });

    test("handles arrays and objects correctly", () => {
        expect(cn(["flex", "items-center"], { "opacity-50": true, "hidden": false })).toBe("flex items-center opacity-50");
    });
});
