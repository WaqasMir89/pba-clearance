import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import { ErrorNotice, Loading } from "./components";
import { amount } from "./format";
import { useResource } from "./hooks";
import {
  recoverRevision,
  RecoveryNotice,
  useResponseCommand,
} from "./responseCommands";
import type { CommandBody } from "./responseCommands";
import type {
  Declaration,
  DisputeCase,
  DisputeRevision,
  DraftSummary,
  EvidenceStatement,
  ObjectionDraft,
  ResponseOptions,
} from "./responseTypes";
import type { Claim, Page } from "./types";

export function SimulationFields({
  declaration,
  disabled,
  values,
}: {
  declaration: Declaration;
  disabled: boolean;
  values?: CommandBody | null;
}) {
  return (
    <>
      <label>
        Simulation date & time · PKT
        <input
          type="datetime-local"
          name="simulation_at"
          defaultValue={
            typeof values?.simulation_at === "string"
              ? values.simulation_at.slice(0, 16)
              : ""
          }
          required
          disabled={disabled}
        />
        <span className="field-hint">
          The actual server timestamp is recorded separately.
        </span>
      </label>
      <label className="checkbox-label">
        <input
          name="declaration_accepted"
          defaultChecked={
            values?.declaration_accepted === true &&
            values.declaration_version === declaration.version
          }
          type="checkbox"
          required
          disabled={disabled}
        />
        <span>{declaration.text}</span>
      </label>
    </>
  );
}

export function simulationFromForm(form: FormData) {
  const value = String(form.get("simulation_at"));
  return `${value}${value.length === 16 ? ":00" : ""}+05:00`;
}

export function ObjectionForm({
  claim,
  organizationId,
  storageKey,
  onPrepared,
  onCancel,
}: {
  claim: Claim;
  organizationId: string;
  storageKey: string;
  onPrepared: (draft: ObjectionDraft) => void;
  onCancel: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const options = useResource<ResponseOptions>(
    "/dispute-options/",
    organizationId,
    attempt,
  );
  const command = useResponseCommand<ObjectionDraft>({
    storageKey: `${storageKey}:prepare:${claim.id}`,
    organizationId,
    path: "/objection-drafts/",
    valid: (body) =>
      body.claim_id === claim.id &&
      typeof body.expected_case_version === "number" &&
      typeof body.disputed_amount === "string",
    matches: (record) =>
      record.claim_id === claim.id && record.agency_id === organizationId,
    recover: async (body) => {
      const result = await api<Page<DraftSummary>>(
        `/objection-drafts/?idempotency_key=${body.idempotency_key}`,
        { organizationId },
      );
      if (!result.count) return null;
      if (result.count !== 1)
        throw new ApiError(
          0,
          "The saved draft result needs an integrity review.",
        );
      return api<ObjectionDraft>(`/objection-drafts/${result.results[0].id}/`, {
        organizationId,
      });
    },
    onSuccess: onPrepared,
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void command.execute({
      claim_id: claim.id,
      expected_case_version: claim.objection_version,
      disputed_amount: String(form.get("disputed_amount")),
      reason_code: String(form.get("reason_code")),
      explanation: String(form.get("explanation")),
      supporting_statement: String(form.get("supporting_statement")),
      source_reference: String(form.get("source_reference")),
      idempotency_key: crypto.randomUUID(),
    });
  }
  return (
    <section
      className="response-form-region"
      aria-label="Prepare objection draft"
    >
      <div className="section-heading">
        <div>
          <h3>Prepare an agency objection</h3>
          <p>
            Claim {claim.invoice_number} · case version{" "}
            {claim.objection_version} · reported PKR{" "}
            {amount(claim.reported_due)}.
          </p>
        </div>
        <span className="badge neutral">Agency-private draft</span>
      </div>
      <RecoveryNotice command={command} />
      {options.loading ? (
        <Loading />
      ) : options.error ? (
        <ErrorNotice
          message={options.error}
          retry={() => setAttempt((v) => v + 1)}
        />
      ) : (
        !command.pending && (
          <form className="stack-form" onSubmit={submit}>
            <div className="form-columns">
              <label>
                Disputed amount · PKR
                <input
                  name="disputed_amount"
                  defaultValue={String(command.lastBody?.disputed_amount || "")}
                  inputMode="decimal"
                  required
                  pattern="[0-9]{1,16}(\.[0-9]{1,2})?"
                  placeholder="e.g. 240.10"
                  disabled={command.busy || command.blocked}
                />
                <span className="field-hint">
                  Positive decimal, no grouping. Maximum reported due:{" "}
                  {amount(claim.reported_due)}.
                </span>
              </label>
              <label>
                Reason category
                <select
                  name="reason_code"
                  defaultValue={
                    typeof command.lastBody?.reason_code === "string"
                      ? command.lastBody.reason_code
                      : undefined
                  }
                  disabled={command.busy || command.blocked}
                >
                  {Object.entries(options.data!.reasons).map(([key, name]) => (
                    <option key={key} value={key}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Objection explanation
              <textarea
                name="explanation"
                defaultValue={String(command.lastBody?.explanation || "")}
                required
                maxLength={3000}
                rows={3}
                disabled={command.busy || command.blocked}
              />
            </label>
            <label>
              Supporting evidence statement
              <textarea
                name="supporting_statement"
                defaultValue={String(
                  command.lastBody?.supporting_statement || "",
                )}
                required
                maxLength={6000}
                rows={4}
                disabled={command.busy || command.blocked}
              />
              <span className="field-hint">
                Fictional plain text only. Original files are not uploaded or
                verified here.
              </span>
            </label>
            <label>
              Supplied source reference (optional)
              <input
                name="source_reference"
                defaultValue={String(command.lastBody?.source_reference || "")}
                maxLength={255}
                disabled={command.busy || command.blocked}
              />
            </label>
            <div className="dialog-actions">
              <button
                type="button"
                className="small-button"
                onClick={onCancel}
                disabled={command.busy}
              >
                Cancel preparation
              </button>
              <button
                className="primary-button"
                disabled={command.busy || command.blocked}
              >
                {command.busy ? "Saving draft…" : "Save private draft"}
              </button>
            </div>
          </form>
        )
      )}
    </section>
  );
}

export function EvidenceForm({
  claimId,
  organizationId,
  storageKey,
  declaration,
  onSaved,
}: {
  claimId: string;
  organizationId: string;
  storageKey: string;
  declaration: Declaration;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const command = useResponseCommand<EvidenceStatement>({
    storageKey: `${storageKey}:evidence:${claimId}`,
    organizationId,
    path: "/claim-evidence/",
    valid: (body) =>
      body.claim_id === claimId &&
      typeof body.statement === "string" &&
      typeof body.simulation_at === "string",
    matches: (record) =>
      record.claim_id === claimId && record.organization_id === organizationId,
    recover: async (body) => {
      const result = await api<Page<EvidenceStatement>>(
        `/claim-evidence/?idempotency_key=${body.idempotency_key}`,
        { organizationId },
      );
      if (!result.count) return null;
      if (result.count !== 1)
        throw new ApiError(
          0,
          "The saved evidence result needs an integrity review.",
        );
      return result.results[0];
    },
    onSuccess: () => {
      setOpen(false);
      onSaved();
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void command.execute({
      claim_id: claimId,
      statement: String(form.get("statement")),
      source_reference: String(form.get("source_reference")),
      simulation_at: simulationFromForm(form),
      declaration_version: declaration.version,
      declaration_accepted: form.get("declaration_accepted") === "on",
      idempotency_key: crypto.randomUUID(),
    });
  }
  return (
    <section
      className="response-form-region"
      aria-label="Supplementary evidence entry"
    >
      <div className="section-heading">
        <div>
          <h3>Supplementary evidence</h3>
          <p>
            Available after ordinary closing. Statements remain unverified and
            do not alter money.
          </p>
        </div>
        <button
          className="small-button"
          onClick={() => setOpen((value) => !value)}
          disabled={command.busy || !!command.pending}
        >
          {open ? "Hide statement form" : "Add evidence statement"}
        </button>
      </div>
      <RecoveryNotice command={command} />
      {open && !command.pending && (
        <form className="stack-form" onSubmit={submit}>
          <label>
            Evidence statement
            <textarea
              name="statement"
              defaultValue={String(command.lastBody?.statement || "")}
              rows={4}
              maxLength={6000}
              required
              disabled={command.busy || command.blocked}
            />
          </label>
          <label>
            Supplied source reference (optional)
            <input
              name="source_reference"
              defaultValue={String(command.lastBody?.source_reference || "")}
              maxLength={255}
              disabled={command.busy || command.blocked}
            />
          </label>
          <SimulationFields
            declaration={declaration}
            values={command.lastBody}
            disabled={command.busy || command.blocked}
          />
          <div>
            <button
              className="primary-button"
              disabled={command.busy || command.blocked}
            >
              {command.busy ? "Recording…" : "Record evidence statement"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export function WithdrawalForm({
  record,
  organizationId,
  storageKey,
  declaration,
  onSaved,
}: {
  record: DisputeCase;
  organizationId: string;
  storageKey: string;
  declaration: Declaration;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const command = useResponseCommand<DisputeRevision>({
    storageKey: `${storageKey}:withdraw:${record.id}`,
    organizationId,
    path: `/disputes/${record.id}/withdraw/`,
    valid: (body) =>
      typeof body.expected_case_version === "number" &&
      typeof body.reason === "string" &&
      typeof body.simulation_at === "string",
    matches: (revision) =>
      revision.case_id === record.id && revision.action === "withdrawn",
    recover: (body) => recoverRevision(organizationId, body, "withdraw"),
    onSuccess: () => {
      setOpen(false);
      onSaved();
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void command.execute({
      expected_case_version: record.current_version,
      reason: String(form.get("reason")),
      simulation_at: simulationFromForm(form),
      declaration_version: declaration.version,
      declaration_accepted: form.get("declaration_accepted") === "on",
      idempotency_key: crypto.randomUUID(),
    });
  }
  if (!command.pending && !command.error && record.state === "withdrawn")
    return null;
  return (
    <section
      className="response-form-region"
      aria-label="Withdraw agency objection"
    >
      <div className="section-heading">
        <div>
          <h3>Withdraw this objection</h3>
          <p>
            Preserves prior versions. Does not pay or clear the reported claim.
          </p>
        </div>
        {record.state === "open" && (
          <button
            className="small-button"
            onClick={() => setOpen((value) => !value)}
            disabled={command.busy || !!command.pending}
          >
            {open ? "Hide withdrawal form" : "Prepare withdrawal"}
          </button>
        )}
      </div>
      <RecoveryNotice command={command} />
      {open && !command.pending && (
        <form className="stack-form" onSubmit={submit}>
          <label>
            Withdrawal reason
            <textarea
              name="reason"
              defaultValue={String(command.lastBody?.reason || "")}
              maxLength={3000}
              rows={3}
              required
              disabled={command.busy || command.blocked}
            />
          </label>
          <SimulationFields
            declaration={declaration}
            values={command.lastBody}
            disabled={command.busy || command.blocked}
          />
          <button
            className="primary-button"
            disabled={command.busy || command.blocked}
          >
            {command.busy ? "Signing…" : "Sign sandbox withdrawal"}
          </button>
        </form>
      )}
    </section>
  );
}
