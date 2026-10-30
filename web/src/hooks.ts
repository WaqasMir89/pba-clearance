import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";

export function useResource<T>(
  path: string,
  organizationId: string,
  revision = 0,
) {
  const key = `${organizationId}:${path}:${revision}`;
  const [state, setState] = useState<{ key: string; data?: T; error?: string }>(
    { key: "" },
  );
  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    let active = true;
    api<T>(path, { organizationId, signal: controller.signal }).then(
      (data) => {
        if (active) setState({ key, data });
      },
      (error: unknown) => {
        if (active && !controller.signal.aborted)
          setState({ key, error: errorMessage(error) });
      },
    );
    return () => {
      active = false;
      controller.abort();
    };
  }, [key, path, organizationId]);
  // Hide the previous scope synchronously, before the next effect runs.
  const current = state.key === key ? state : { key };
  return { ...current, loading: !current.data && !current.error };
}

export function useDebounced(value: string) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), 220);
    return () => window.clearTimeout(timer);
  }, [value]);
  return debounced;
}
