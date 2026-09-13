import {
    api,
    getAdminToken,
    setAdminToken,
    onAdminTokenChange,
    getAuthToken,
    getAuthUser,
    setAuthSession,
    clearAuthSession,
    onAuthChange,
    scoreBand,
    providerTone,
    providerHint,
    PROVIDER_TONES,
    isErrorEvent,
    STATUSES,
    STATUS_META,
} from "./api";

describe("api helper logic and state", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    describe("admin token management", () => {
        test("getAdminToken returns empty string when not set", () => {
            expect(getAdminToken()).toBe("");
        });

        test("setAdminToken sets and getAdminToken retrieves token", () => {
            setAdminToken("test-secret-token");
            expect(getAdminToken()).toBe("test-secret-token");
        });

        test("setAdminToken with empty/null removes token", () => {
            setAdminToken("token-to-remove");
            expect(getAdminToken()).toBe("token-to-remove");
            setAdminToken("");
            expect(getAdminToken()).toBe("");
        });

        test("onAdminTokenChange listens to token update events", () => {
            const handler = jest.fn();
            const cleanup = onAdminTokenChange(handler);

            setAdminToken("event-token");
            expect(handler).toHaveBeenCalledTimes(1);

            cleanup();
            setAdminToken("another-token");
            expect(handler).toHaveBeenCalledTimes(1);
        });

        test("request interceptor attaches X-Admin-Token header when present", async () => {
            setAdminToken("interceptor-admin-123");
            const config = { headers: {} };
            // Retrieve request interceptor handler
            const interceptor = api.interceptors.request.handlers[0];
            const modifiedConfig = interceptor.fulfilled(config);
            expect(modifiedConfig.headers["X-Admin-Token"]).toBe("interceptor-admin-123");
        });

        test("request interceptor omits X-Admin-Token header when absent", async () => {
            setAdminToken("");
            const config = { headers: {} };
            const interceptor = api.interceptors.request.handlers[0];
            const modifiedConfig = interceptor.fulfilled(config);
            expect(modifiedConfig.headers["X-Admin-Token"]).toBeUndefined();
        });
    });

    describe("auth session management", () => {
        test("getAuthToken and getAuthUser return empty/null when not set", () => {
            expect(getAuthToken()).toBe("");
            expect(getAuthUser()).toBeNull();
        });

        test("setAuthSession sets token and user profile in storage", () => {
            setAuthSession("jwt-test-token-xyz", { name: "Agent Test", email: "test@estatex.io" });
            expect(getAuthToken()).toBe("jwt-test-token-xyz");
            expect(getAuthUser()).toEqual({ name: "Agent Test", email: "test@estatex.io" });
        });

        test("clearAuthSession clears token and user profile", () => {
            setAuthSession("jwt-temp", { name: "Temp" });
            clearAuthSession();
            expect(getAuthToken()).toBe("");
            expect(getAuthUser()).toBeNull();
        });

        test("onAuthChange listens to auth session update events", () => {
            const handler = jest.fn();
            const cleanup = onAuthChange(handler);

            setAuthSession("new-token", { name: "User" });
            expect(handler).toHaveBeenCalledTimes(1);

            cleanup();
            setAuthSession("another-token", null);
            expect(handler).toHaveBeenCalledTimes(1);
        });

        test("request interceptor attaches Bearer Authorization header when token exists", () => {
            setAuthSession("secret-jwt-token-99", { name: "Agent" });
            const config = { headers: {} };
            const interceptor = api.interceptors.request.handlers[0];
            const modifiedConfig = interceptor.fulfilled(config);
            expect(modifiedConfig.headers["Authorization"]).toBe("Bearer secret-jwt-token-99");
        });
    });

    describe("scoring and statuses", () => {
        test("scoreBand calculates correct tiers", () => {
            expect(scoreBand(100).label).toBe("Elite");
            expect(scoreBand(85).label).toBe("Elite");
            expect(scoreBand(84).label).toBe("Qualified");
            expect(scoreBand(70).label).toBe("Qualified");
            expect(scoreBand(69).label).toBe("Nurture");
            expect(scoreBand(40).label).toBe("Nurture");
            expect(scoreBand(39).label).toBe("Cold");
            expect(scoreBand(0).label).toBe("Cold");
        });

        test("STATUSES contains the 7 canonical pipeline statuses", () => {
            expect(STATUSES).toEqual([
                "NEW",
                "CALLING",
                "IN_CONVERSATION",
                "QUALIFIED",
                "HOT",
                "NURTURE",
                "BOOKED",
            ]);
            STATUSES.forEach((s) => {
                expect(STATUS_META[s]).toBeDefined();
                expect(STATUS_META[s].color).toBeDefined();
                expect(STATUS_META[s].label).toBeDefined();
            });
        });
    });

    describe("provider status helpers", () => {
        test("providerTone returns MOCK when mode is not LIVE", () => {
            expect(providerTone({ mode: "MOCK" })).toBe(PROVIDER_TONES.MOCK);
            expect(providerTone({ mode: "DEMO" })).toBe(PROVIDER_TONES.MOCK);
        });

        test("providerTone returns LIVE_OK when mode is LIVE and last_ok is true or null", () => {
            expect(providerTone({ mode: "LIVE", last_ok: true })).toBe(PROVIDER_TONES.LIVE_OK);
            expect(providerTone({ mode: "LIVE", last_ok: null })).toBe(PROVIDER_TONES.LIVE_OK);
        });

        test("providerTone returns LIVE_ERROR when mode is LIVE and last_ok is false", () => {
            expect(providerTone({ mode: "LIVE", last_ok: false })).toBe(PROVIDER_TONES.LIVE_ERROR);
        });

        test("providerHint formats tooltip lines correctly", () => {
            const mockProvider = {
                capability: "LLM Extraction",
                mode: "MOCK",
                missing_env: ["GROQ_API_KEY"],
            };
            expect(providerHint(mockProvider)).toContain("LLM Extraction");
            expect(providerHint(mockProvider)).toContain("Mocked — set GROQ_API_KEY");

            const liveOkProvider = {
                capability: "Email Delivery",
                mode: "LIVE",
                last_ok: true,
                calls: 12,
                failures: 0,
            };
            expect(providerHint(liveOkProvider)).toContain("Last call OK");
            expect(providerHint(liveOkProvider)).toContain("12 calls · 0 failures");

            const liveErrorProvider = {
                capability: "Calendar Sync",
                mode: "LIVE",
                last_ok: false,
                last_status: 401,
                last_error: "Unauthorized key",
            };
            expect(providerHint(liveErrorProvider)).toContain("Last call failed — HTTP 401");
            expect(providerHint(liveErrorProvider)).toContain("Unauthorized key");
        });
    });

    describe("error events helper", () => {
        test("isErrorEvent detects error kind and failure keywords", () => {
            expect(isErrorEvent({ kind: "error" })).toBe(true);
            expect(isErrorEvent({ reason: "network failed" })).toBe(true);
            expect(isErrorEvent({ reason: "api timeout occurred" })).toBe(true);
            expect(isErrorEvent({ reason: "rate limit blocked" })).toBe(true);
            expect(isErrorEvent({ reason: "lead rejected" })).toBe(true);
            expect(isErrorEvent({ reason: "normal status update" })).toBe(false);
            expect(isErrorEvent({ kind: "status_change", reason: "scheduled call" })).toBe(false);
        });
    });
});
