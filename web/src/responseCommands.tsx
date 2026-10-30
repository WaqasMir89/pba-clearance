import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { FormError } from "./components";
import { definiteRejection, forget, remember } from "./intakeCommands";
import type { DisputeRevision, RevisionSummary } from "./responseTypes";
import type { Page } from "./types";

export type CommandBody = Record<string, string | number | boolean>;
type SavedCommand = {
  version: 1;
  organizationId: string;
  path: string;
  body: CommandBody;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const responseKey = (userId: string, organizationId: string) =>
  `clearance:responses:${userId}:${organizationId}`;

function readSaved(
  key: string,
  organizationId: string,
  path: string,
  valid: (body: CommandBody) => boolean,
) {
  const text = sessionStorage.getItem(key);
  if (!text) return null;
  const saved = JSON.parse(text) as SavedCommand;
  if (
    text.length > 50000 ||
    saved.version !== 1 ||
    saved.organizationId !== organizationId ||
    saved.path !== path ||
    typeof saved.body !== "object" ||
    saved.body === null ||
    Array.isArray(saved.body) ||
    Object.values(saved.body).some(
      (value) => !["string", "number", "boolean"].includes(typeof value),
    ) ||
    typeof saved.body.idempotency_key !== "string" ||
    !uuid.test(saved.body.idempotency_key) ||
    !valid(saved.body)
  ) {
    throw new Error("Invalid saved command");
  }
  return saved;
}

export function useResponseCommand<T extends { id: string }>({
  storageKey,
  organizationId,
  path,
  valid,
  matches,
  recover,
  onSuccess,
}: {
  storageKey: string;
  organizationId: string;
  path: string;
  valid: (body: CommandBody) => boolean;
  matches: (record: T, body: CommandBody) => boolean;
  recover: (body: CommandBody) => Promise<T | null>;
  onSuccess: (record: T) => void;
}) {
  const [initial] = useState(() => {
    try {
      return {
        command: readSaved(storageKey, organizationId, path, valid),
        error: null as unknown,
      };
    } catch {
      return {
        command: null,
        error: new ApiError(
          0,
          "The saved recovery record cannot be read. Keep this tab and restore its storage before submitting.",
        ),
      };
    }
  });
  const [pending, setPending] = useState(initial.command);
  const [lastBody, setLastBody] = useState<CommandBody | null>(
    initial.command?.body || null,
  );
  const [error, setError] = useState<unknown>(initial.error);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const current = useRef(initial.command);
  const mounted = useRef(false);
  function finish(record: T, body: CommandBody) {
    if (!uuid.test(record.id) || !matches(record, body))
      throw new ApiError(
        0,
        "The returned record differs from the saved command. Request an integrity review.",
      );
    try {
      forget(storageKey);
    } catch {
      /* The protected record can be confirmed again after reload. */
    }
    window.dispatchEvent(new Event("clearance-response-commands"));
    current.current = null;
    if (mounted.current) {
      setPending(null);
      setError(null);
      setMessage("");
      onSuccess(record);
    }
  }
  async function run(mode: "check" | "retry" | "new", body?: CommandBody) {
    if (
      inFlight.current ||
      initial.error ||
      (mode === "new" && current.current)
    )
      return;
    const saved =
      mode === "new" && body
        ? { version: 1 as const, organizationId, path, body }
        : current.current;
    if (!saved || !valid(saved.body)) return;
    inFlight.current = true;
    if (mounted.current) {
      setBusy(true);
      setError(null);
      setMessage("");
    }
    try {
      if (mode !== "new") {
        const found = await recover(saved.body);
        if (found) {
          finish(found, saved.body);
          return;
        }
        if (mode === "check") {
          if (mounted.current)
            setMessage(
              "No result is visible yet. Check again or explicitly retry the saved command.",
            );
          return;
        }
      }
      remember(storageKey, saved);
      window.dispatchEvent(new Event("clearance-response-commands"));
      current.current = saved;
      if (mounted.current) {
        setLastBody(saved.body);
        setPending(saved);
      }
      try {
        const record = await api<T>(path, { organizationId, body: saved.body });
        finish(record, saved.body);
      } catch (commandError) {
        const found = await recover(saved.body);
        if (found) {
          finish(found, saved.body);
          return;
        }
        if (definiteRejection(commandError)) {
          try {
            forget(storageKey);
          } catch {
            /* Preserve server authority if local storage is unavailable. */
          }
          current.current = null;
          window.dispatchEvent(new Event("clearance-response-commands"));
          if (mounted.current) setPending(null);
        } else if (mounted.current)
          setMessage(
            "The outcome is unconfirmed. The original command is preserved for a protected check and retry.",
          );
        if (mounted.current) setError(commandError);
      }
    } catch (error) {
      if (mounted.current) {
        setError(error);
        setMessage(
          current.current
            ? "The result could not be checked. Keep this tab; the saved command is preserved."
            : "No command was sent. Recovery storage must be available first.",
        );
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  useEffect(() => {
    mounted.current = true;
    if (initial.command) void run("check");
    return () => {
      mounted.current = false;
    };
  }, []);
  return {
    lastBody,
    pending,
    error,
    message,
    busy,
    blocked: !!initial.error,
    execute: (body: CommandBody) => run("new", body),
    check: () => run("check"),
    retry: () => run("retry"),
  };
}

export function RecoveryNotice({
  command,
}: {
  command: Pick<
    ReturnType<typeof useResponseCommand>,
    "pending" | "error" | "message" | "busy" | "check" | "retry"
  >;
}) {
  return (
    <>
      {command.pending && (
        <div className="recovery-notice" role="status">
          <strong>Saved command awaiting confirmation</strong>
          <p>
            Its original values and command reference will be retained across a
            reload in this tab.
          </p>
          <details className="intake-help">
            <summary>Review saved command values</summary>
            <dl className="receipt-facts">
              {Object.entries(command.pending.body).map(([key, value]) => (
                <div className="wide-field" key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd className="statement-text">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
          <div className="button-row">
            <button
              className="small-button"
              onClick={command.check}
              disabled={command.busy}
            >
              Check saved result
            </button>
            <button
              className="primary-button"
              onClick={command.retry}
              disabled={command.busy}
            >
              Retry saved command
            </button>
          </div>
        </div>
      )}
      {command.message && (
        <p className="muted recovery-copy" role="status">
          {command.message}
        </p>
      )}
      <FormError error={command.error} />
    </>
  );
}

export async function recoverRevision(
  organizationId: string,
  body: CommandBody,
  commandType: "submit" | "withdraw",
) {
  const page = await api<Page<RevisionSummary>>(
    `/dispute-revisions/?idempotency_key=${body.idempotency_key}&command_type=${commandType}`,
    { organizationId },
  );
  if (!page.count) return null;
  if (page.count !== 1)
    throw new ApiError(
      0,
      "Multiple command results require an integrity review.",
    );
  return api<DisputeRevision>(`/dispute-revisions/${page.results[0].id}/`, {
    organizationId,
  });
}
