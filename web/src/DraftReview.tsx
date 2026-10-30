import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import { ErrorNotice, FormError, Loading } from "./components";
import { amount, dateTime } from "./format";
import { useResource } from "./hooks";
import { downloadText, forget, sha256 } from "./intakeCommands";
import {
  recoverRevision,
  RecoveryNotice,
  useResponseCommand,
} from "./responseCommands";
import { SimulationFields, simulationFromForm } from "./ResponseForms";
import type { DisputeRevision, ObjectionDraft } from "./responseTypes";
import type { Membership } from "./types";

export function DraftReview({
  id,
  membership,
  storageKey,
  onChanged,
}: {
  id: string;
  membership: Membership;
  storageKey: string;
  onChanged: () => void;
}) {
  const organizationId = membership.organization.id;
  const [attempt, setAttempt] = useState(0);
  const draft = useResource<ObjectionDraft>(
    `/objection-drafts/${id}/`,
    organizationId,
    attempt,
  );
  useEffect(() => {
    if (draft.data?.submission_id) {
      try {
        forget(`${storageKey}:sign:${id}`);
      } catch {
        /* A future protected read can confirm it again. */
      }
    }
  }, [draft.data?.submission_id, id, storageKey]);
  if (draft.loading) return <Loading />;
  if (draft.error)
    return (
      <ErrorNotice
        message={draft.error}
        retry={() => setAttempt((value) => value + 1)}
      />
    );
  const record = draft.data!;
  return (
    <section className="response-workspace" aria-label="Objection draft review">
      <div className="section-heading">
        <div>
          <p className="eyebrow">AGENCY-PRIVATE SOURCE DRAFT</p>
          <h2>{record.claim_snapshot.invoice_number}</h2>
          <p>
            {record.claim_snapshot.agency_name} ·{" "}
            {record.claim_snapshot.channel_name}
          </p>
        </div>
        <button
          className="small-button"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Refresh draft review
        </button>
      </div>
      <dl className="receipt-facts">
        <div>
          <dt>Proposed disputed amount · PKR</dt>
          <dd>{amount(record.disputed_amount)}</dd>
        </div>
        <div>
          <dt>Original reported due · PKR</dt>
          <dd>{amount(record.claim_snapshot.reported_due)}</dd>
        </div>
        <div>
          <dt>Client · cycle</dt>
          <dd>
            {record.claim_snapshot.client_name}
            <br />
            {record.claim_snapshot.cycle_code}
          </dd>
        </div>
        <div>
          <dt>Prepared by · PKT</dt>
          <dd>
            {record.created_by}
            <br />
            {dateTime(record.created_at)}
          </dd>
        </div>
        <div>
          <dt>Base case version</dt>
          <dd>{record.base_version}</dd>
        </div>
        <div>
          <dt>Current case version / state</dt>
          <dd>
            {record.preview.current_version} · {record.preview.current_state}
          </dd>
        </div>
        <div className="wide-field">
          <dt>
            Objection explanation · {record.reason_code.replaceAll("_", " ")}
          </dt>
          <dd className="statement-text">{record.explanation}</dd>
        </div>
        <div className="wide-field">
          <dt>Supporting evidence statement</dt>
          <dd className="statement-text">{record.supporting_statement}</dd>
        </div>
        {record.source_reference && (
          <div className="wide-field">
            <dt>Supplied reference · unverified</dt>
            <dd>{record.source_reference}</dd>
          </div>
        )}
        <div className="wide-field">
          <dt>Draft SHA-256</dt>
          <dd className="digest">{record.content_hash}</dd>
        </div>
      </dl>
      {record.submission_id ? (
        <RevisionReceipt
          id={record.submission_id}
          organizationId={organizationId}
        />
      ) : (
        <>
          {record.preview.issues.length > 0 && (
            <div className="form-error" role="alert">
              <p>This draft cannot be signed.</p>
              <ul>
                {record.preview.issues.map((issue) => (
                  <li key={issue.code}>{issue.message}</li>
                ))}
              </ul>
            </div>
          )}
          {membership.can_sign_objections ? (
            <SignDraft
              key={`${record.id}:${record.preview.preview_hash}`}
              record={record}
              organizationId={organizationId}
              storageKey={storageKey}
              onSigned={() => {
                setAttempt((value) => value + 1);
                onChanged();
              }}
            />
          ) : (
            <p className="muted preparer-note">
              A current agency approver must review and sign this draft.
              Preparing it does not open an objection.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function SignDraft({
  record,
  organizationId,
  storageKey,
  onSigned,
}: {
  record: ObjectionDraft;
  organizationId: string;
  storageKey: string;
  onSigned: () => void;
}) {
  const command = useResponseCommand<DisputeRevision>({
    storageKey: `${storageKey}:sign:${record.id}`,
    organizationId,
    path: `/objection-drafts/${record.id}/submit/`,
    valid: (body) =>
      typeof body.expected_preview_hash === "string" &&
      typeof body.simulation_at === "string",
    matches: (revision) =>
      revision.receipt.draft_id === record.id &&
      revision.agency_id === organizationId,
    recover: (body) => recoverRevision(organizationId, body, "submit"),
    onSuccess: onSigned,
  });
  const window = record.preview.window;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void command.execute({
      expected_preview_hash: record.preview.preview_hash,
      simulation_at: simulationFromForm(form),
      declaration_version: record.preview.declaration.version,
      declaration_accepted: form.get("declaration_accepted") === "on",
      idempotency_key: crypto.randomUUID(),
    });
  }
  return (
    <section
      className="response-form-region"
      aria-label="Sign agency objection"
    >
      <h3>Sign the sandbox objection</h3>
      {window && (
        <div className="window-context">
          <p className="window-times">
            {dateTime(window.opens_at)} ≤ simulation &lt;{" "}
            {dateTime(window.closes_at)} PKT
          </p>
          <p className="muted">
            Explicit fictional response window · {window.source_reference}
          </p>
          <p className="digest">{window.source_sha256}</p>
        </div>
      )}
      <RecoveryNotice command={command} />
      {!command.pending && (
        <form className="stack-form" onSubmit={submit}>
          <SimulationFields
            declaration={record.preview.declaration}
            values={command.lastBody}
            disabled={command.busy || command.blocked}
          />
          <div>
            <button
              className="primary-button"
              disabled={
                command.busy ||
                command.blocked ||
                record.preview.issues.length > 0 ||
                !window
              }
            >
              {command.busy ? "Signing…" : "Sign sandbox objection"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export function RevisionReceipt({
  id,
  organizationId,
}: {
  id: string;
  organizationId: string;
}) {
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const revision = useResource<DisputeRevision>(
    `/dispute-revisions/${id}/`,
    organizationId,
    attempt,
  );
  async function download() {
    if (!revision.data || busy) return;
    setBusy(true);
    setError(null);
    setVerified(false);
    try {
      const text = await api<string>(`/dispute-revisions/${id}/receipt/`, {
        organizationId,
        responseType: "text",
      });
      if (
        (await sha256(new TextEncoder().encode(text))) !==
        revision.data.content_hash
      )
        throw new ApiError(
          0,
          "Receipt hash mismatch. Download stopped; request an integrity review.",
        );
      downloadText(
        text,
        `dispute-receipt-${id}.json`,
        "application/json;charset=utf-8",
      );
      setVerified(true);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  if (revision.loading) return <Loading />;
  if (revision.error)
    return (
      <ErrorNotice
        message={revision.error}
        retry={() => setAttempt((value) => value + 1)}
      />
    );
  const record = revision.data!;
  return (
    <section className="receipt-panel" aria-label="Signed objection receipt">
      <div className="section-heading">
        <div>
          <p className="eyebrow">SIGNED SANDBOX REVISION</p>
          <h3>
            Version {record.version} · {record.action}
          </h3>
          <p>
            Reported due is unchanged. Financial and enforcement effects: none.
          </p>
        </div>
        <button className="small-button" onClick={download} disabled={busy}>
          {busy ? "Verifying…" : "Verify & download objection receipt"}
        </button>
      </div>
      {verified && (
        <p className="success-notice" role="status">
          SHA-256 verified. Objection receipt download started.
        </p>
      )}
      <FormError error={error} />
      <dl className="receipt-facts">
        <div>
          <dt>Disputed amount · PKR</dt>
          <dd>{amount(record.disputed_amount)}</dd>
        </div>
        <div>
          <dt>Signer</dt>
          <dd>{record.created_by}</dd>
        </div>
        <div>
          <dt>Actual recorded time · PKT</dt>
          <dd>{dateTime(record.created_at)}</dd>
        </div>
        <div>
          <dt>Simulation time · PKT</dt>
          <dd>{dateTime(record.simulation_at)}</dd>
        </div>
        <div className="wide-field">
          <dt>Explanation</dt>
          <dd className="statement-text">{record.receipt.explanation}</dd>
        </div>
        {record.receipt.supporting_statement && (
          <div className="wide-field">
            <dt>Supporting statement · unverified</dt>
            <dd className="statement-text">
              {record.receipt.supporting_statement}
            </dd>
          </div>
        )}
        {record.receipt.source_reference && (
          <div className="wide-field">
            <dt>Supplied reference</dt>
            <dd>{record.receipt.source_reference}</dd>
          </div>
        )}
        <div className="wide-field">
          <dt>Revision reference · SHA-256</dt>
          <dd className="digest">
            {record.id}
            <br />
            {record.content_hash}
          </dd>
        </div>
        {record.receipt.previous_revision_hash && (
          <div className="wide-field">
            <dt>Previous revision SHA-256</dt>
            <dd className="digest">{record.receipt.previous_revision_hash}</dd>
          </div>
        )}
        <div className="wide-field">
          <dt>Original complaint receipt SHA-256</dt>
          <dd className="digest">
            {record.receipt.claim.source_submission_hash}
          </dd>
        </div>
      </dl>
      <details className="intake-help">
        <summary>Accepted declaration</summary>
        <p className="muted">{record.receipt.declaration.text}</p>
      </details>
    </section>
  );
}
