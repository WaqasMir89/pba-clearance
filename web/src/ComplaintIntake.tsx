import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import { Empty, ErrorNotice, FormError, Loading, Pager } from "./components";
import { amount, dateTime } from "./format";
import { useDebounced, useResource } from "./hooks";
import {
  base64,
  definiteRejection,
  downloadText,
  forget,
  readFiling,
  readStage,
  recoveryKey,
  remember,
  sha256,
} from "./intakeCommands";
import type { PendingStage } from "./intakeCommands";
import { Receipt } from "./Receipt";
import type {
  Cycle,
  FilingPayload,
  ImportDetail,
  ImportListEntry,
  IntakeOptions,
  Membership,
  Page,
  RowStatus,
  Submission,
} from "./types";

const statusLabel: Record<RowStatus, string> = {
  ready: "Ready",
  invalid: "Invalid",
  review: "Needs review",
  duplicate: "Duplicate",
};

function selectedImport(key: string) {
  try {
    return sessionStorage.getItem(`${key}:selected`) || "";
  } catch {
    return "";
  }
}

export function ComplaintIntake({
  userId,
  membership,
  cycle,
  cycles,
  revision,
  refresh,
}: {
  userId: string;
  membership: Membership;
  cycle?: Cycle;
  cycles: Cycle[];
  revision: number;
  refresh: () => void;
}) {
  const organizationId = membership.organization.id;
  const storageKey = recoveryKey(userId, organizationId);
  const [selected, setSelected] = useState(() => selectedImport(storageKey));
  const [uploadOpen, setUploadOpen] = useState(() => {
    try {
      return (
        !selectedImport(storageKey) ||
        !!sessionStorage.getItem(`${storageKey}:stage`)
      );
    } catch {
      return true;
    }
  });
  const [pageState, setPageState] = useState({ cycleId: cycle?.id, page: 1 });
  const page = pageState.cycleId === cycle?.id ? pageState.page : 1;
  const setPage = (value: number) =>
    setPageState({ cycleId: cycle?.id, page: value });
  const list = useResource<Page<ImportListEntry>>(
    `/complaint-imports/?page_size=10&page=${page}${cycle ? `&cycle_id=${cycle.id}` : ""}`,
    organizationId,
    revision,
  );
  function select(id: string) {
    setSelected(id);
    setUploadOpen(false);
    try {
      sessionStorage.setItem(`${storageKey}:selected`, id);
    } catch {
      /* Selection is optional; command recovery is mandatory. */
    }
  }
  return (
    <>
      <section aria-label="Staged imports">
        <div className="section-heading">
          <div>
            <h2>Channel imports</h2>
            <p>
              {cycle ? `Listing ${cycle.code}.` : "All accessible cycles."} Only
              ready rows can be filed.
            </p>
          </div>
          <div className="button-row">
            <button className="small-button" onClick={refresh}>
              Refresh
            </button>
            <button
              className="primary-button"
              onClick={() => setUploadOpen((v) => !v)}
            >
              {uploadOpen ? "Hide upload" : "Stage CSV"}
            </button>
          </div>
        </div>
        {uploadOpen && (
          <Upload
            organizationId={organizationId}
            storageKey={storageKey}
            cycle={cycle}
            onStaged={(id) => {
              select(id);
              setPage(1);
              refresh();
            }}
          />
        )}
        {list.loading ? (
          <Loading />
        ) : list.error ? (
          <ErrorNotice message={list.error} retry={refresh} />
        ) : list.data?.results.length ? (
          <>
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Channel import history"
            >
              <table>
                <caption className="sr-only">
                  CSV imports for the reference cycle
                </caption>
                <thead>
                  <tr>
                    <th>Source file</th>
                    <th>Staged by / PKT</th>
                    <th>Rows</th>
                    <th>State</th>
                    <th>
                      <span className="sr-only">Review</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.results.map((entry) => (
                    <tr
                      key={entry.id}
                      className={selected === entry.id ? "selected-row" : ""}
                    >
                      <td>
                        <button
                          className="text-button source-link"
                          onClick={() => select(entry.id)}
                          aria-label={`Open ${entry.source_filename}`}
                        >
                          {entry.source_filename}
                        </button>
                        <span className="subject-reference">
                          {entry.cycle_code}
                        </span>
                      </td>
                      <td>
                        {entry.created_by}
                        <span className="subject-reference">
                          {dateTime(entry.created_at)}
                        </span>
                      </td>
                      <td>{entry.row_count}</td>
                      <td>
                        <span
                          className={`badge ${entry.submission_id ? "" : "neutral"}`}
                        >
                          {entry.submission_id ? "Filed" : "Staged"}
                        </span>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => select(entry.id)}
                          aria-label={`Review ${entry.source_filename}`}
                        >
                          Review ↗
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              count={list.data.count}
              page={page}
              hasNext={!!list.data.next}
              setPage={setPage}
            />
          </>
        ) : (
          <Empty title="No imports in this cycle">
            Stage a fictional CSV to review its invoice rows. Staging does not
            file a complaint.
          </Empty>
        )}
      </section>
      {selected && (
        <ImportReview
          key={selected}
          id={selected}
          storageKey={storageKey}
          membership={membership}
          cycles={cycles}
          referenceCycleId={cycle?.id}
          revision={revision}
          refresh={refresh}
        />
      )}
    </>
  );
}

function Upload({
  organizationId,
  storageKey,
  cycle,
  onStaged,
}: {
  organizationId: string;
  storageKey: string;
  cycle?: Cycle;
  onStaged: (id: string) => void;
}) {
  const key = `${storageKey}:stage`;
  const [initial] = useState(() => {
    try {
      return { pending: readStage(key), error: null as unknown };
    } catch (error) {
      return { pending: null, error };
    }
  });
  const [pending, setPending] = useState<PendingStage | null>(initial.pending);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(initial.error);
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const [guideQuery, setGuideQuery] = useState("");
  const guideSearch = useDebounced(guideQuery);
  const [attempt, setAttempt] = useState(0);
  const options = useResource<IntakeOptions>(
    `/complaint-intake/options/?q=${encodeURIComponent(guideSearch)}`,
    organizationId,
    attempt,
  );
  async function lookup(saved: PendingStage) {
    const result = await api<Page<ImportListEntry>>(
      `/complaint-imports/?idempotency_key=${saved.idempotency_key}`,
      { organizationId },
    );
    if (!result.count) return false;
    const match = result.results[0];
    if (
      result.count !== 1 ||
      match.cycle_id !== saved.cycle_id ||
      match.source_sha256 !== saved.source_sha256 ||
      match.source_filename !== saved.source_filename
    ) {
      throw new ApiError(
        0,
        "The recovered import differs from the saved upload. Request an integrity review.",
      );
    }
    await api<ImportDetail>(`/complaint-imports/${match.id}/`, {
      organizationId,
    });
    forget(key);
    setPending(null);
    onStaged(match.id);
    return true;
  }
  async function check() {
    if (!pending || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!(await lookup(pending)))
        setRecoveryMessage(
          "No staged result is visible yet. Reselect the original CSV to retry the saved upload, or check again.",
        );
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (initial.pending) void check();
  }, []);
  async function stage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !file || !options.data || initial.error || (!pending && !cycle))
      return;
    setBusy(true);
    setError(null);
    setRecoveryMessage("");
    let saved: PendingStage | null = pending;
    try {
      if (saved && (await lookup(saved))) return;
      if (!file.size || file.size > options.data.max_source_bytes)
        throw new ApiError(
          400,
          "Choose a nonempty CSV file of at most 256 KiB.",
        );
      const bytes = new Uint8Array(await file.arrayBuffer());
      const hash = await sha256(bytes);
      if (
        saved &&
        (saved.source_sha256 !== hash || saved.source_filename !== file.name)
      )
        throw new ApiError(
          0,
          "Reselect the original filename and unchanged CSV. A pending upload cannot be replaced with different content.",
        );
      saved = saved || {
        version: 1,
        cycle_id: cycle!.id,
        source_filename: file.name,
        source_sha256: hash,
        idempotency_key: crypto.randomUUID(),
      };
      // Persist only metadata; source file bytes stay in memory.
      remember(key, saved);
      setPending(saved);
      let commandError: unknown;
      try {
        const result = await api<ImportDetail>("/complaint-imports/", {
          organizationId,
          body: {
            cycle_id: saved.cycle_id,
            source_filename: saved.source_filename,
            csv_base64: base64(bytes),
            idempotency_key: saved.idempotency_key,
          },
        });
        forget(key);
        setPending(null);
        onStaged(result.id);
        return;
      } catch (error) {
        commandError = error;
      }
      // Read before any replay after an uncertain response.
      if (await lookup(saved)) return;
      if (definiteRejection(commandError)) {
        forget(key);
        setPending(null);
      } else
        setRecoveryMessage(
          "Upload outcome is unconfirmed. Check for its staged result before retrying the saved command.",
        );
      setError(commandError);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  async function template() {
    setError(null);
    try {
      downloadText(
        await api<string>("/complaint-import-template/", {
          responseType: "text",
        }),
        "complaint-import-template.csv",
        "text/csv;charset=utf-8",
      );
    } catch (error) {
      setError(error);
    }
  }
  return (
    <div className="upload-region">
      <div className="section-heading">
        <div>
          <h3>Stage a fictional CSV</h3>
          <p>UTF-8 · maximum 256 KiB / 500 rows · PKR decimal amounts.</p>
        </div>
        <button className="text-button" onClick={template}>
          Download blank template ↓
        </button>
      </div>
      {options.error && (
        <ErrorNotice
          message={options.error}
          retry={() => setAttempt((v) => v + 1)}
        />
      )}
      {pending && (
        <div className="recovery-notice" role="status">
          <strong>Saved upload awaiting confirmation</strong>
          <p>
            {pending.source_filename} · its original cycle and command are
            preserved.
          </p>
          <button className="small-button" onClick={check} disabled={busy}>
            Check upload result
          </button>
        </div>
      )}
      {recoveryMessage && (
        <p className="muted recovery-copy" role="status">
          {recoveryMessage}
        </p>
      )}
      <form className="upload-form" onSubmit={stage}>
        <label htmlFor="complaint-csv">
          {pending ? "Reselect the original CSV" : "CSV file"}
          <input
            id="complaint-csv"
            name="csv"
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            disabled={busy}
          />
        </label>
        <div>
          <span className="field-hint">
            {pending
              ? "Retry keeps the saved cycle and file hash."
              : cycle
                ? `For ${cycle.code}`
                : "Select a candidate cycle first."}
          </span>
          <button
            className="primary-button"
            disabled={
              busy ||
              !file ||
              !options.data ||
              !!initial.error ||
              (!pending && !cycle?.policy.is_demo)
            }
          >
            {busy
              ? "Checking upload…"
              : pending
                ? "Retry saved upload"
                : "Stage for review"}
          </button>
        </div>
      </form>
      <FormError error={error} />
      <details className="intake-help">
        <summary>CSV format and eligible client codes</summary>
        <p className="muted">
          Use ISO dates and ungrouped decimal strings, such as 1180.00.
          Principal + GST must equal the original invoice total. Reduced
          reported due needs an explanation. A delivery reference is required
          for a ready row.
        </p>
        {options.data && (
          <>
            <p className="mono header-list">
              Required: {options.data.required_headers.join(", ")}
            </p>
            <p className="mono header-list">
              Optional: {options.data.optional_headers.join(", ")}
            </p>
          </>
        )}
        <label className="guide-search">
          Find eligible client codes
          <input
            value={guideQuery}
            onChange={(event) => setGuideQuery(event.target.value)}
            placeholder="Client code or legal name"
          />
        </label>
        {options.loading ? (
          <Loading />
        ) : (
          options.data && (
            <>
              <p className="muted small-copy">
                Showing {options.data.clients.length} of{" "}
                {options.data.client_count} matching clients. These shares
                establish visibility only.
              </p>
              <ul className="code-list">
                {options.data.clients.map((client) => (
                  <li key={client.id}>
                    <strong>{client.code}</strong> · {client.legal_name}
                    <span>
                      Agency codes:{" "}
                      {client.agency_ids
                        .map(
                          (id) =>
                            options.data!.agencies.find(
                              (agency) => agency.id === id,
                            )?.code,
                        )
                        .filter(Boolean)
                        .join(", ") || "No eligible demo agency"}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )
        )}
      </details>
    </div>
  );
}

function ImportReview({
  id,
  storageKey,
  membership,
  cycles,
  referenceCycleId,
  revision,
  refresh,
}: {
  id: string;
  storageKey: string;
  membership: Membership;
  cycles: Cycle[];
  referenceCycleId?: string;
  revision: number;
  refresh: () => void;
}) {
  const organizationId = membership.organization.id;
  const resource = useResource<ImportDetail>(
    `/complaint-imports/${id}/`,
    organizationId,
    revision,
  );
  useEffect(() => {
    if (resource.data?.submission_id) {
      // A protected read confirms the outcome even if the tab reloaded before the POST returned.
      try {
        forget(`${storageKey}:filing:${id}`);
      } catch {
        /* A later recovery read can confirm it again. */
      }
    }
  }, [resource.data?.submission_id, storageKey, id]);
  const [filter, setFilter] = useState<RowStatus | "all">("all");
  const [page, setPage] = useState(1);
  if (resource.loading) return <Loading />;
  if (resource.error)
    return <ErrorNotice message={resource.error} retry={refresh} />;
  const detail = resource.data!;
  const cycle = cycles.find((entry) => entry.id === detail.cycle_id);
  const preview = detail.preview;
  const rows = preview.rows.filter(
    (row) => filter === "all" || row.status === filter,
  );
  return (
    <section className="import-review" aria-label="Import review">
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {detail.preview_current
              ? "CURRENT VALIDATION"
              : "ARCHIVED FILING REVIEW"}
          </p>
          <h2>{detail.source_filename}</h2>
          <p>
            {detail.cycle_code} · {detail.row_count} source rows · staged by{" "}
            {detail.created_by}
          </p>
        </div>
        <button className="small-button" onClick={refresh}>
          Refresh review
        </button>
      </div>
      {referenceCycleId && referenceCycleId !== detail.cycle_id && (
        <p className="recovery-notice">
          This import belongs to <strong>{detail.cycle_code}</strong>. Changing
          the reference selector does not change its filing cycle.
        </p>
      )}
      <dl className="source-facts">
        <div>
          <dt>Original CSV SHA-256</dt>
          <dd className="digest">{detail.source_sha256}</dd>
        </div>
        <div>
          <dt>
            {detail.preview_current
              ? "Checked at · PKT"
              : "Filed preview checked at · PKT"}
          </dt>
          <dd>{dateTime(preview.checked_at)}</dd>
        </div>
      </dl>
      <div className="review-counts" aria-label="Validation counts">
        {(["ready", "invalid", "review", "duplicate"] as RowStatus[]).map(
          (status) => (
            <div key={status}>
              <span>{statusLabel[status]}</span>
              <strong>{preview.counts[status]}</strong>
            </div>
          ),
        )}
      </div>
      <div className="review-total">
        <span>
          {detail.submission_id
            ? "Filed reported amount"
            : "Ready reported amount"}
        </span>
        <strong>PKR {amount(preview.ready_reported_total)}</strong>
        <small>Unverified channel report</small>
      </div>
      <div className="list-toolbar">
        <label className="status-filter">
          Show rows
          <select
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value as RowStatus | "all");
              setPage(1);
            }}
          >
            <option value="all">All outcomes</option>
            {Object.entries(statusLabel).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className="muted">
          {detail.submission_id
            ? "Review preserved exactly as filed."
            : "Invalid, review and duplicate rows will be excluded."}
        </p>
      </div>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Source row validation"
      >
        <table className="review-table">
          <caption className="sr-only">
            Source rows and validation feedback
          </caption>
          <thead>
            <tr>
              <th>Row / invoice</th>
              <th>Agency / client</th>
              <th className="numeric">Reported due · PKR</th>
              <th>Outcome & feedback</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice((page - 1) * 25, page * 25).map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>
                    {row.values.invoice_number || "Missing invoice"}
                  </strong>
                  <span className="subject-reference">
                    Row {row.number} · {row.values.financial_year}
                  </span>
                  <details className="row-source">
                    <summary>Source fields</summary>
                    <dl>
                      {Object.entries(row.values).map(([field, value]) => (
                        <div key={field}>
                          <dt>{field.replaceAll("_", " ")}</dt>
                          <dd>{value || "—"}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                </td>
                <td>
                  {row.canonical?.agency_name || row.values.agency_code || "—"}
                  <span className="subject-reference">
                    {row.canonical?.client_name ||
                      row.values.client_code ||
                      "—"}
                  </span>
                </td>
                <td className="numeric">
                  {row.canonical?.reported_due
                    ? amount(row.canonical.reported_due)
                    : row.values.reported_due || "—"}
                </td>
                <td>
                  <span className={`badge row-status ${row.status}`}>
                    {statusLabel[row.status]}
                  </span>
                  {row.issues.length > 0 && (
                    <ul className="row-issues">
                      {row.issues.map((issue, i) => (
                        <li key={`${issue.code}-${i}`}>
                          <strong>{issue.field.replaceAll("_", " ")}</strong>:{" "}
                          {issue.message}
                        </li>
                      ))}
                    </ul>
                  )}
                  {row.duplicate_of_row && (
                    <p className="field-hint">
                      Repeats source row {row.duplicate_of_row}.
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <Empty title="No rows with this outcome">
          Choose another outcome to inspect this import.
        </Empty>
      )}
      <Pager
        count={rows.length}
        page={page}
        hasNext={page * 25 < rows.length}
        setPage={setPage}
      />
      {detail.submission_id ? (
        <Receipt
          key={detail.submission_id}
          id={detail.submission_id}
          organizationId={organizationId}
        />
      ) : membership.can_file_complaints ? (
        <FilingPanel
          key={`${id}:${preview.preview_hash}`}
          detail={detail}
          cycle={cycle}
          organizationId={organizationId}
          storageKey={storageKey}
          onFiled={refresh}
        />
      ) : (
        <div className="preparer-note">
          <h3>Ready for a channel approver</h3>
          <p className="muted">
            Your role can stage and review. A channel approver must sign the
            declaration and file the ready rows from this workspace.
          </p>
        </div>
      )}
    </section>
  );
}

function FilingPanel({
  detail,
  cycle,
  organizationId,
  storageKey,
  onFiled,
}: {
  detail: ImportDetail;
  cycle?: Cycle;
  organizationId: string;
  storageKey: string;
  onFiled: () => void;
}) {
  const key = `${storageKey}:filing:${detail.id}`;
  const [initial] = useState(() => {
    try {
      return { pending: readFiling(key), error: null as unknown };
    } catch (error) {
      return { pending: null, error };
    }
  });
  const [pending, setPending] = useState<FilingPayload | null>(initial.pending);
  const [simulation, setSimulation] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(initial.error);
  const [message, setMessage] = useState("");
  const options = useResource<IntakeOptions>(
    "/complaint-intake/options/",
    organizationId,
  );
  const open = cycle?.milestones.find(
    (milestone) => milestone.code === "complaint_open",
  );
  const close = cycle?.milestones.find(
    (milestone) => milestone.code === "complaint_close",
  );
  async function reconcile() {
    const current = await api<ImportDetail>(
      `/complaint-imports/${detail.id}/`,
      { organizationId },
    );
    if (!current.submission_id) return false;
    await api<Submission>(`/complaint-submissions/${current.submission_id}/`, {
      organizationId,
    });
    forget(key);
    setPending(null);
    onFiled();
    return true;
  }
  async function check() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!(await reconcile()))
        setMessage(
          "No receipt is visible yet. Retry the saved filing with its original time, declaration and review, or check again.",
        );
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (initial.pending) void check();
  }, []);
  async function retrySaved() {
    if (busy || !pending) return;
    setBusy(true);
    setError(null);
    let replay = false;
    try {
      replay = !(await reconcile());
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
    if (replay) void send(pending);
  }
  async function send(saved: FilingPayload) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setMessage("");
    let persisted = false;
    try {
      // Persist before sending. Every uncertain retry uses this exact payload and UUID.
      remember(key, saved);
      persisted = true;
      setPending(saved);
      let commandError: unknown;
      try {
        await api<Submission>(`/complaint-imports/${detail.id}/submit/`, {
          organizationId,
          body: saved,
        });
        forget(key);
        setPending(null);
        onFiled();
        return;
      } catch (error) {
        commandError = error;
      }
      if (await reconcile()) return;
      if (definiteRejection(commandError)) {
        forget(key);
        setPending(null);
      } else
        setMessage(
          "Filing outcome is unconfirmed. Keep the saved command and check for a receipt before retrying.",
        );
      setError(commandError);
    } catch (error) {
      setError(error);
      setMessage(
        persisted || pending
          ? "The result could not be checked. Your saved command is preserved in this tab."
          : "No filing was sent. Recovery storage must be available before filing.",
      );
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!options.data || !accepted || !simulation || pending || initial.error)
      return;
    void send({
      expected_preview_hash: detail.preview.preview_hash,
      simulation_at: `${simulation}${simulation.length === 16 ? ":00" : ""}+05:00`,
      declaration_version: options.data.declaration.version,
      declaration_accepted: true,
      idempotency_key: crypto.randomUUID(),
    });
  }
  return (
    <section className="filing-panel" aria-label="Approve sandbox filing">
      <div className="section-heading">
        <div>
          <p className="eyebrow">CHANNEL APPROVER</p>
          <h2>File ready rows</h2>
          <p>
            {detail.preview.counts.ready} rows · PKR{" "}
            {amount(detail.preview.ready_reported_total)} reported due. All
            other rows are excluded.
          </p>
        </div>
        <span className="badge candidate">Sandbox only</span>
      </div>
      {pending ? (
        <div className="recovery-notice" role="status">
          <strong>Saved filing awaiting confirmation</strong>
          <p>
            Simulation: {dateTime(pending.simulation_at)} PKT. Original review
            and declaration are preserved.
          </p>
          <div className="button-row">
            <button className="small-button" onClick={check} disabled={busy}>
              Check filing result
            </button>
            <button
              className="primary-button"
              onClick={retrySaved}
              disabled={busy}
            >
              Retry saved filing
            </button>
          </div>
        </div>
      ) : (
        <form className="stack-form filing-form" onSubmit={submit}>
          <div className="filing-clock">
            <p className="muted">
              Use a simulation time inside this import's candidate window. The
              receipt separately records the actual submission time.
            </p>
            <p className="window-times">
              {open && close
                ? `${dateTime(open.occurs_at)} ≤ simulation < ${dateTime(close.occurs_at)} PKT`
                : "The original candidate window is unavailable. Reload its calendar before filing."}
            </p>
            <label>
              Simulation date & time · PKT
              <input
                name="simulation_at"
                type="datetime-local"
                required
                value={simulation}
                onChange={(event) => setSimulation(event.target.value)}
                disabled={busy}
              />
            </label>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              required
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
              disabled={busy || !options.data}
            />
            <span>
              {options.data?.declaration.text ||
                "Loading the required declaration…"}
            </span>
          </label>
          {options.error && (
            <p className="form-error" role="alert">
              {options.error}
            </p>
          )}
          <div>
            <button
              className="primary-button"
              disabled={
                busy ||
                !accepted ||
                !simulation ||
                !options.data ||
                !open ||
                !close ||
                !detail.preview.counts.ready ||
                !!initial.error
              }
            >
              {busy ? "Filing…" : "File ready rows in sandbox"}
            </button>
          </div>
        </form>
      )}
      {message && (
        <p className="muted recovery-copy" role="status">
          {message}
        </p>
      )}
      <FormError error={error} />
      {error && !pending ? (
        <p className="field-hint">
          Refresh the review after correcting the source or a changed preview. A
          corrected source must be staged as a new import.
        </p>
      ) : null}
    </section>
  );
}
