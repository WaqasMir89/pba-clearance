import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
import { Dialog, Empty, ErrorNotice, Loading, Pager } from "./components";
import { DraftReview } from "./DraftReview";
import { amount } from "./format";
import { useDebounced, useResource } from "./hooks";
import { ClaimDetail } from "./ReportedClaims";
import { responseKey } from "./responseCommands";
import type { DisputeCase, DraftSummary } from "./responseTypes";
import type { Cycle, Membership, Page } from "./types";

export function ObjectionRegister({
  membership,
  userId,
  cycle,
  revision,
  refresh,
}: {
  membership: Membership;
  userId: string;
  cycle?: Cycle;
  revision: number;
  refresh: () => void;
}) {
  const organizationId = membership.organization.id;
  const key = responseKey(userId, organizationId);
  const [view, setView] = useState<"cases" | "drafts">("cases");
  const [query, setQuery] = useState("");
  const search = useDebounced(query);
  const [pageState, setPageState] = useState({
    view,
    cycle: cycle?.id,
    page: 1,
  });
  const page =
    pageState.view === view && pageState.cycle === cycle?.id
      ? pageState.page
      : 1;
  const setPage = (page: number) =>
    setPageState({ view, cycle: cycle?.id, page });
  const [selectedClaim, setSelectedClaim] = useState("");
  const [selectedDraft, setSelectedDraft] = useState("");
  const path =
    view === "cases"
      ? `/disputes/?q=${encodeURIComponent(search)}`
      : "/objection-drafts/?";
  const records = useResource<Page<DisputeCase | DraftSummary>>(
    `${path}&page=${page}${cycle ? `&cycle_id=${cycle.id}` : ""}`,
    organizationId,
    revision,
  );
  return (
    <section aria-label="Objection register">
      <PendingResponses
        key={`${key}:${revision}`}
        storageKey={key}
        organizationId={organizationId}
        openDraft={setSelectedDraft}
        openClaim={setSelectedClaim}
      />
      <div className="section-heading">
        <div>
          <h2>
            {view === "cases"
              ? "Submitted agency objections"
              : "Private agency drafts"}
          </h2>
          <p>
            {view === "cases"
              ? "Signed versions follow the claim's parties. Disputed amounts do not reduce reported due."
              : "Drafts are visible only within this agency until an approver signs."}
          </p>
        </div>
        <button className="small-button" onClick={refresh}>
          Refresh
        </button>
      </div>
      <div className="list-toolbar">
        {view === "cases" ? (
          <label className="search-field">
            <span className="sr-only">Search objection invoice</span>
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="Search submitted invoice number…"
            />
          </label>
        ) : (
          <p className="muted">
            Prepare a draft from a reported claim's detail.
          </p>
        )}
        {membership.organization.kind === "agency" && (
          <label className="status-filter">
            Register view
            <select
              value={view}
              onChange={(event) =>
                setView(event.target.value as "cases" | "drafts")
              }
            >
              <option value="cases">Submitted cases</option>
              <option value="drafts">Agency-private drafts</option>
            </select>
          </label>
        )}
      </div>
      {records.loading ? (
        <Loading />
      ) : records.error ? (
        <ErrorNotice message={records.error} retry={refresh} />
      ) : records.data?.results.length ? (
        <>
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label={
              view === "cases"
                ? "Submitted objection cases"
                : "Agency-private objection drafts"
            }
          >
            <table>
              <caption className="sr-only">
                {view === "cases"
                  ? "Submitted agency cases"
                  : "Agency-private staged drafts"}
              </caption>
              <thead>
                <tr>
                  <th>Invoice / client</th>
                  <th>Channel / agency</th>
                  <th className="numeric">Disputed · PKR</th>
                  <th>State / version</th>
                  <th>
                    <span className="sr-only">Review</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {records.data.results.map((record) =>
                  "claim_snapshot" in record ? (
                    <tr key={record.id}>
                      <td>
                        <button
                          className="text-button source-link"
                          aria-label={`Open draft ${record.claim_snapshot.invoice_number}`}
                          onClick={() => setSelectedDraft(record.id)}
                        >
                          {record.claim_snapshot.invoice_number}
                        </button>
                        <span className="subject-reference">
                          {record.claim_snapshot.client_name}
                        </span>
                      </td>
                      <td>
                        {record.claim_snapshot.channel_name}
                        <span className="subject-reference">
                          {record.claim_snapshot.agency_name}
                        </span>
                      </td>
                      <td className="numeric">
                        {amount(record.disputed_amount)}
                      </td>
                      <td>
                        {record.submission_id ? "Signed" : "Prepared"}
                        <span className="subject-reference">
                          Base v{record.base_version} · {record.created_by}
                        </span>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setSelectedDraft(record.id)}
                        >
                          Review draft ↗
                        </button>
                      </td>
                    </tr>
                  ) : (
                    <tr key={record.id}>
                      <td>
                        <button
                          className="text-button source-link"
                          aria-label={`Open objection ${record.invoice_number}`}
                          onClick={() => setSelectedClaim(record.claim_id)}
                        >
                          {record.invoice_number}
                        </button>
                        <span className="subject-reference">
                          {record.client_name}
                        </span>
                      </td>
                      <td>
                        {record.channel_name}
                        <span className="subject-reference">
                          {record.agency_name}
                        </span>
                      </td>
                      <td className="numeric">
                        {amount(record.current_disputed_amount)}
                      </td>
                      <td>
                        <span
                          className={`badge ${record.state === "open" ? "candidate" : "neutral"}`}
                        >
                          {record.state} · v{record.current_version}
                        </span>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setSelectedClaim(record.claim_id)}
                        >
                          Review case ↗
                        </button>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <Pager
            count={records.data.count}
            page={page}
            hasNext={!!records.data.next}
            setPage={setPage}
          />
        </>
      ) : (
        <Empty
          title={
            view === "cases" ? "No submitted objections" : "No private drafts"
          }
        >
          {view === "cases"
            ? "Only signed agency objections appear here. Drafts and evidence statements do not open a case."
            : "Open a reported claim to prepare an agency-private objection draft."}
        </Empty>
      )}
      {selectedClaim && (
        <ClaimDetail
          key={selectedClaim}
          id={selectedClaim}
          membership={membership}
          userId={userId}
          onChanged={refresh}
          onClose={() => setSelectedClaim("")}
        />
      )}
      {selectedDraft && (
        <Dialog
          title="Objection draft"
          busy={false}
          onClose={() => setSelectedDraft("")}
        >
          <DraftReview
            id={selectedDraft}
            membership={membership}
            storageKey={key}
            onChanged={refresh}
          />
        </Dialog>
      )}
    </section>
  );
}

type PendingSource = {
  key: string;
  label: string;
  target: string;
  kind: "claim" | "draft" | "case";
};
function pendingSources(prefix: string): PendingSource[] {
  const results: PendingSource[] = [];
  for (const key of Object.keys(sessionStorage).filter(
    (key) => key.startsWith(prefix) && !key.includes(":selected-"),
  )) {
    const saved = JSON.parse(sessionStorage.getItem(key)!);
    if (typeof saved.path !== "string" || !saved.body) continue;
    const sign = saved.path.match(
      /^\/objection-drafts\/([a-f0-9-]{36})\/submit\/$/,
    );
    const withdraw = saved.path.match(
      /^\/disputes\/([a-f0-9-]{36})\/withdraw\/$/,
    );
    if (sign)
      results.push({
        key,
        label: "Objection signature",
        target: sign[1],
        kind: "draft",
      });
    else if (withdraw)
      results.push({
        key,
        label: "Objection withdrawal",
        target: withdraw[1],
        kind: "case",
      });
    else if (
      (saved.path === "/objection-drafts/" ||
        saved.path === "/claim-evidence/") &&
      typeof saved.body.claim_id === "string" &&
      /^[a-f0-9-]{36}$/.test(saved.body.claim_id)
    )
      results.push({
        key,
        label:
          saved.path === "/claim-evidence/"
            ? "Evidence statement"
            : "Objection preparation",
        target: saved.body.claim_id,
        kind: "claim",
      });
  }
  return results;
}

function PendingResponses({
  storageKey,
  organizationId,
  openClaim,
  openDraft,
}: {
  storageKey: string;
  organizationId: string;
  openClaim: (id: string) => void;
  openDraft: (id: string) => void;
}) {
  const [initial, setInitial] = useState(() => {
    try {
      return { records: pendingSources(`${storageKey}:`), error: "" };
    } catch {
      return {
        records: [],
        error:
          "A saved response command could not be read. Keep this tab and restore its storage before submitting.",
      };
    }
  });
  const [error, setError] = useState(initial.error);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const update = () => {
      try {
        setInitial({ records: pendingSources(`${storageKey}:`), error: "" });
      } catch {
        setError(
          "A saved response command could not be read. Keep this tab and restore its storage.",
        );
      }
    };
    window.addEventListener("clearance-response-commands", update);
    return () =>
      window.removeEventListener("clearance-response-commands", update);
  }, [storageKey]);
  async function open(record: PendingSource) {
    setBusy(true);
    setError("");
    try {
      if (record.kind === "draft") openDraft(record.target);
      else if (record.kind === "claim") openClaim(record.target);
      else
        openClaim(
          (
            await api<DisputeCase>(`/disputes/${record.target}/`, {
              organizationId,
            })
          ).claim_id,
        );
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {error && <ErrorNotice message={error} />}
      {initial.records.length > 0 && (
        <section
          className="recovery-notice"
          aria-label="Saved response commands"
        >
          <strong>Response commands awaiting confirmation</strong>
          <p>
            Open each source to check the protected result before an explicit
            retry.
          </p>
          <ul>
            {initial.records.map((record) => (
              <li key={record.key}>
                {record.label}
                <button
                  className="text-button"
                  onClick={() => open(record)}
                  disabled={busy}
                >
                  Open saved source ↗
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
