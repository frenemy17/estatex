import { useEffect, useRef } from "react";

/**
 * Poll `fn` on an interval, but only while the tab is visible.
 *
 * A backgrounded tab stops polling entirely and refetches once on return, so a
 * dashboard left open in another window costs nothing. `fn` is read from a ref,
 * so an inline closure does not restart the timer on every render.
 */
export function usePoll(fn, intervalMs, deps = []) {
    const latest = useRef(fn);
    latest.current = fn;

    useEffect(() => {
        let timer = null;
        const tick = () => latest.current();
        const start = () => {
            if (!timer) timer = setInterval(tick, intervalMs);
        };
        const stop = () => {
            if (timer) clearInterval(timer);
            timer = null;
        };
        const onVisibility = () => {
            if (document.hidden) return stop();
            tick();
            start();
        };

        tick();
        if (!document.hidden) start();
        document.addEventListener("visibilitychange", onVisibility);
        return () => {
            stop();
            document.removeEventListener("visibilitychange", onVisibility);
        };
    }, [intervalMs, ...deps]);
}
