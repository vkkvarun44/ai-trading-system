import { useEffect, useState } from "react";

export function usePolling(fetcher, intervalMs = 8000, initialValue = null, options = {}) {
  const { enabled = true, resetOnDisable = false, pauseWhenHidden = true } = options;
  const [data, setData] = useState(initialValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setError("");
      if (resetOnDisable) {
        setData(initialValue);
      }
      return undefined;
    }

    let active = true;
    let timeoutId = null;
    let inFlight = false;

    function scheduleNext(delay = intervalMs) {
      if (!active) {
        return;
      }
      timeoutId = window.setTimeout(load, delay);
    }

    async function load() {
      if (!active || inFlight) {
        return;
      }
      if (pauseWhenHidden && typeof document !== "undefined" && document.hidden) {
        scheduleNext(intervalMs);
        return;
      }

      inFlight = true;
      try {
        const result = await fetcher();
        if (!active) {
          return;
        }
        setData(result);
        setError("");
      } catch (err) {
        if (active) {
          setError(err.message || "Polling request failed.");
        }
      } finally {
        inFlight = false;
        if (active) {
          setLoading(false);
          scheduleNext(intervalMs);
        }
      }
    }

    load();

    function handleVisibilityChange() {
      if (!active || !pauseWhenHidden) {
        return;
      }
      if (!document.hidden) {
        if (timeoutId) {
          window.clearTimeout(timeoutId);
          timeoutId = null;
        }
        load();
      }
    }

    if (pauseWhenHidden && typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    return () => {
      active = false;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (pauseWhenHidden && typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    };
  }, [enabled, fetcher, initialValue, intervalMs, pauseWhenHidden, resetOnDisable]);

  return { data, loading, error, setData };
}
