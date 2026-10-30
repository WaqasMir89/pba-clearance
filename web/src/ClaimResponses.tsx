import { useState } from "react";
import { Empty, ErrorNotice, Loading, Pager } from "./components";
import { DraftReview, RevisionReceipt } from "./DraftReview";
import { amount, dateTime } from "./format";
import { useResource } from "./hooks";
import { EvidenceForm, ObjectionForm, WithdrawalForm } from "./ResponseForms";
import { responseKey } from "./responseCommands";
import type {
  DisputeCase,
  EvidenceStatement,
  ResponseOptions,
  ResponseWindow,
  RevisionSummary,
} from "./responseTypes";
import type { Claim, Membership, Page } from "./types";

function preference(key: string) {
  try {
    return sessionStorage.getItem(key) || "";
  } catch {
    return "";
  }
}
const timingLabels = {
  before_window: "Before response window",
  within_window: "Within response window",
  late: "Late evidence",
  window_unknown: "Window not configured",
};

export function ClaimResponses({
  claim,
  membership,
  userId,
  onChanged,
  onDraftPrepared,
}: {
  claim: Claim;
  membership: Membership;
  userId: string;
  onChanged: () => void;
  onDraftPrepared: () => void;
}) {
  const organizationId = membership.organization.id;
  const key = responseKey(userId, organizationId);
  const selectedKey = `${key}:selected-draft:${claim.id}`;
  const [draftId, setDraftId] = useState(() =>
    membership.organization.kind === "agency" ? preference(selectedKey) : "",
  );
  const [preparing, setPreparing] = useState(
    () => !!preference(`${key}:prepare:${claim.id}`),
  );
  const [evidencePage, setEvidencePage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [selectedRevision, setSelectedRevision] = useState("");
  const options = useResource<ResponseOptions>(
    "/dispute-options/",
    organizationId,
  );
  const cases = useResource<Page<DisputeCase>>(
    `/disputes/?claim_id=${claim.id}`,
    organizationId,
  );
  const windows = useResource<Page<ResponseWindow>>(
    `/dispute-windows/?cycle_id=${claim.cycle_id}`,
    organizationId,
  );
  const current = cases.data?.results[0];
  const revisions = useResource<Page<RevisionSummary>>(
    `/dispute-revisions/?claim_id=${claim.id}${current ? `&case_id=${current.id}` : ""}&page_size=10&page=${historyPage}`,
    organizationId,
  );
  const evidence = useResource<Page<EvidenceStatement>>(
    `/claim-evidence/?claim_id=${claim.id}&page_size=10&page=${evidencePage}`,
    organizationId,
  );
  function selectDraft(value: string) {
    setDraftId(value);
    try {
      if (value) sessionStorage.setItem(selectedKey, value);
      else sessionStorage.removeItem(selectedKey);
    } catch {
      /* Selection is optional; pending commands use mandatory storage. */
    }
  }
  const baseClaim = current
    ? {
        ...claim,
        objection_version: current.current_version,
        objection_state: current.state,
        disputed_amount: current.current_disputed_amount,
      }
    : claim;
  return (
    <section
      className="response-workspace"
      aria-label="Agency objection and evidence"
    >
      <div className="section-heading">
        <div>
          <h2>Agency response</h2>
          <p>
            Disputed amounts are shown separately. No financial or enforcement
            effect is applied.
          </p>
        </div>
        <button className="small-button" onClick={onChanged}>
          Refresh response
        </button>
      </div>
      {draftId && (
        <>
          <button className="text-button" onClick={() => selectDraft("")}>
            ← Back to response history
          </button>
          <DraftReview
            key={draftId}
            id={draftId}
            membership={membership}
            storageKey={key}
            onChanged={onChanged}
          />
        </>
      )}
      {!draftId && (
        <>
          {cases.loading ? (
            <Loading />
          ) : cases.error ? (
            <ErrorNotice message={cases.error} retry={onChanged} />
          ) : (
            <div className="response-state">
              <span
                className={`badge ${current?.state === "open" ? "candidate" : "neutral"}`}
              >
                {current
                  ? `${current.state} · version ${current.current_version}`
                  : "No signed objection"}
              </span>
              <strong>
                Disputed PKR{" "}
                {amount(current?.current_disputed_amount || "0.00")}
              </strong>
            </div>
          )}
          {windows.error ? (
            <ErrorNotice message={windows.error} retry={onChanged} />
          ) : windows.data?.results[0] ? (
            <p className="muted window-context">
              Fictional response window:{" "}
              {dateTime(windows.data.results[0].opens_at)} ≤ simulation &lt;{" "}
              {dateTime(windows.data.results[0].closes_at)} PKT.
            </p>
          ) : (
            !windows.loading && (
              <p className="recovery-notice">
                No response window is configured for this claim's cycle.
                Ordinary signing is blocked; supplementary evidence remains
                available.
              </p>
            )
          )}
          {membership.can_stage_objections && !preparing && (
            <button
              className="primary-button"
              onClick={() => setPreparing(true)}
              disabled={cases.loading || !!cases.error}
            >
              {current
                ? current.state === "withdrawn"
                  ? "Prepare reopening draft"
                  : "Prepare amended draft"
                : "Prepare objection draft"}
            </button>
          )}
          {preparing && membership.can_stage_objections && (
            <ObjectionForm
              claim={baseClaim}
              organizationId={organizationId}
              storageKey={key}
              onCancel={() => setPreparing(false)}
              onPrepared={(record) => {
                setPreparing(false);
                selectDraft(record.id);
                onDraftPrepared();
              }}
            />
          )}
          {!preparing && (
            <>
              {membership.can_sign_objections && current && options.data && (
                <WithdrawalForm
                  key={current.id}
                  record={current}
                  organizationId={organizationId}
                  storageKey={key}
                  declaration={options.data.declarations.withdraw}
                  onSaved={onChanged}
                />
              )}
              <section
                className="response-history"
                aria-label="Signed objection history"
              >
                <div className="section-heading">
                  <div>
                    <h3>Signed revision history</h3>
                    <p>
                      Earlier versions retain their original facts and receipt
                      hashes.
                    </p>
                  </div>
                </div>
                {revisions.loading ? (
                  <Loading />
                ) : revisions.error ? (
                  <ErrorNotice message={revisions.error} retry={onChanged} />
                ) : revisions.data?.results.length ? (
                  <>
                    <div
                      className="table-scroll"
                      tabIndex={0}
                      role="region"
                      aria-label="Objection revisions"
                    >
                      <table>
                        <caption className="sr-only">
                          Signed objection revisions
                        </caption>
                        <thead>
                          <tr>
                            <th>Version / action</th>
                            <th>Signer / actual PKT</th>
                            <th className="numeric">Disputed · PKR</th>
                            <th>
                              <span className="sr-only">Receipt</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {revisions.data.results.map((record) => (
                            <tr key={record.id}>
                              <td>
                                v{record.version} · {record.action}
                              </td>
                              <td>
                                {record.created_by}
                                <span className="subject-reference">
                                  {dateTime(record.created_at)}
                                </span>
                              </td>
                              <td className="numeric">
                                {amount(record.disputed_amount)}
                              </td>
                              <td>
                                <button
                                  className="text-button"
                                  aria-label={`View objection receipt version ${record.version}`}
                                  onClick={() =>
                                    setSelectedRevision((value) =>
                                      value === record.id ? "" : record.id,
                                    )
                                  }
                                >
                                  Receipt ↗
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <Pager
                      count={revisions.data.count}
                      page={historyPage}
                      hasNext={!!revisions.data.next}
                      setPage={setHistoryPage}
                    />
                  </>
                ) : (
                  <Empty title="No signed revision">
                    An agency approver's signed submission will appear here.
                  </Empty>
                )}
                {selectedRevision && (
                  <RevisionReceipt
                    key={selectedRevision}
                    id={selectedRevision}
                    organizationId={organizationId}
                  />
                )}
              </section>
              {options.error && (
                <ErrorNotice message={options.error} retry={onChanged} />
              )}
              {membership.can_add_evidence && options.data && (
                <EvidenceForm
                  claimId={claim.id}
                  organizationId={organizationId}
                  storageKey={key}
                  declaration={options.data.declarations.evidence}
                  onSaved={onChanged}
                />
              )}
              <section
                className="evidence-history"
                aria-label="Recorded evidence statements"
              >
                <div className="section-heading">
                  <div>
                    <h3>Recorded evidence statements</h3>
                    <p>
                      Plain-text statements and supplied references, without
                      original-document verification.
                    </p>
                  </div>
                </div>
                {evidence.loading ? (
                  <Loading />
                ) : evidence.error ? (
                  <ErrorNotice message={evidence.error} retry={onChanged} />
                ) : evidence.data?.results.length ? (
                  <>
                    {evidence.data.results.map((record) => (
                      <article className="evidence-entry" key={record.id}>
                        <div className="section-heading">
                          <div>
                            <h3>{record.organization_name}</h3>
                            <p>
                              {record.created_by} · recorded{" "}
                              {dateTime(record.created_at)} PKT
                            </p>
                          </div>
                          <span
                            className={`badge ${record.timing === "late" ? "candidate" : "neutral"}`}
                          >
                            {timingLabels[record.timing]}
                          </span>
                        </div>
                        <p className="statement-text">{record.statement}</p>
                        {record.source_reference && (
                          <p className="muted small-copy">
                            Supplied reference: {record.source_reference}
                          </p>
                        )}
                        <p className="field-hint small-copy">
                          Simulation: {dateTime(record.simulation_at)} PKT ·
                          unverified · no financial effect
                        </p>
                        <details className="intake-help">
                          <summary>Evidence record reference and hash</summary>
                          <p className="digest">
                            {record.id}
                            <br />
                            {record.content_hash}
                          </p>
                        </details>
                      </article>
                    ))}
                    <Pager
                      count={evidence.data.count}
                      page={evidencePage}
                      hasNext={!!evidence.data.next}
                      setPage={setEvidencePage}
                    />
                  </>
                ) : (
                  <Empty title="No supplementary statements">
                    Authorized participants can add a statement after ordinary
                    closing.
                  </Empty>
                )}
              </section>
            </>
          )}
        </>
      )}
    </section>
  );
}
