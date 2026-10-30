import { useState } from "react";
import { ClaimResponses } from "./ClaimResponses";
import { Dialog, Empty, ErrorNotice, Loading, Pager } from "./components";
import { amount, dateOnly, dateTime } from "./format";
import { useDebounced, useResource } from "./hooks";
import { Receipt } from "./Receipt";
import type { ClaimGroup } from "./responseTypes";
import type { Claim, ClaimSummary, Cycle, Membership, Page } from "./types";

export function ReportedClaims({
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
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [group, setGroup] = useState("reports");
  const search = useDebounced(query);
  const filters = `q=${encodeURIComponent(search)}${cycle ? `&cycle_id=${cycle.id}` : ""}`;
  const list = useResource<Page<Claim>>(
    `/claims/?${filters}&page=${page}`,
    organizationId,
    revision,
  );
  const summary = useResource<ClaimSummary>(
    `/claims/summary/?${filters}`,
    organizationId,
    revision,
  );
  return (
    <section aria-label="Reported claims register">
      <div className="section-heading">
        <div>
          <h2>
            {membership.organization.kind === "agency"
              ? "Reports against this agency"
              : "Filed channel reports"}
          </h2>
          <p>
            {cycle ? cycle.code : "All visible cycles"} · reported amounts have
            not been verified as liability or settlement.
          </p>
        </div>
        <button className="small-button" onClick={refresh}>
          Refresh
        </button>
      </div>
      {summary.error ? (
        <ErrorNotice message={summary.error} retry={refresh} />
      ) : (
        <div className="claim-summary response-summary">
          <div>
            <span>Visible filed claims</span>
            <strong>{summary.data?.count ?? "—"}</strong>
          </div>
          <div>
            <span>Reported due · PKR</span>
            <strong>
              {summary.data ? amount(summary.data.reported_due_total) : "—"}
            </strong>
          </div>
          <div>
            <span>Separately disputed · PKR</span>
            <strong>
              {summary.data ? amount(summary.data.disputed_amount_total) : "—"}
            </strong>
            <small>
              {summary.data?.active_objection_count ?? "—"} active objections
            </small>
          </div>
          <p>
            Accepted credits: unknown · Verified settlement: unknown · Remaining
            reportable balance: unknown.
            <br />
            Objections do not reduce reported due or authorize an enforcement
            hold.
          </p>
        </div>
      )}
      <div className="list-toolbar">
        <label className="search-field">
          <span className="sr-only">Search invoice number</span>
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder="Search invoice number…"
          />
        </label>
        <label className="status-filter">
          Report view
          <select
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          >
            <option value="reports">Invoice reports</option>
            <option value="channel">By channel</option>
            <option value="client">By client</option>
            <option value="cycle">By cycle</option>
          </select>
        </label>
      </div>
      {group !== "reports" ? (
        <ClaimBreakdown
          key={`${group}:${filters}`}
          group={group}
          filters={filters}
          organizationId={organizationId}
          revision={revision}
          refresh={refresh}
        />
      ) : list.loading ? (
        <Loading />
      ) : list.error ? (
        <ErrorNotice message={list.error} retry={refresh} />
      ) : list.data?.results.length ? (
        <>
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Visible filed claims"
          >
            <table>
              <caption className="sr-only">Scoped reported claims</caption>
              <thead>
                <tr>
                  <th>Invoice / year</th>
                  <th>Channel</th>
                  <th>Agency / client</th>
                  <th className="numeric">Original total · PKR</th>
                  <th className="numeric">Reported due · PKR</th>
                  <th className="numeric">Disputed · PKR</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((claim) => (
                  <tr key={claim.id}>
                    <td>
                      <button
                        className="text-button source-link"
                        aria-label={`Open claim ${claim.invoice_number}`}
                        onClick={() => setSelected(claim.id)}
                      >
                        {claim.invoice_number}
                      </button>
                      <span className="subject-reference">
                        {claim.financial_year}
                      </span>
                    </td>
                    <td>{claim.channel_name}</td>
                    <td>
                      {claim.agency_name}
                      <span className="subject-reference">
                        {claim.client_name}
                      </span>
                    </td>
                    <td className="numeric">{amount(claim.invoice_total)}</td>
                    <td className="numeric">{amount(claim.reported_due)}</td>
                    <td className="numeric">
                      {amount(claim.disputed_amount)}
                      <span className="subject-reference">
                        {claim.objection_state === "none"
                          ? "No objection"
                          : `${claim.objection_state} · v${claim.objection_version}`}
                      </span>
                    </td>
                    <td>
                      <button
                        className="text-button"
                        aria-label={`View claim ${claim.invoice_number}`}
                        onClick={() => setSelected(claim.id)}
                      >
                        View ↗
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
        <Empty
          title={
            query
              ? "No matching invoice reports"
              : "No filed reports in this cycle"
          }
        >
          {query
            ? "Try a different invoice number."
            : "Staged or excluded source rows do not appear here. Only claims filed against this workspace's permitted scope are listed."}
        </Empty>
      )}
      {selected && (
        <ClaimDetail
          key={selected}
          id={selected}
          membership={membership}
          userId={userId}
          onChanged={refresh}
          onClose={() => setSelected("")}
        />
      )}
    </section>
  );
}

export function ClaimDetail({
  id,
  membership,
  userId,
  onChanged,
  onClose,
}: {
  id: string;
  membership: Membership;
  userId: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const organizationId = membership.organization.id;
  const canViewReceipt = membership.organization.kind !== "agency";
  const [attempt, setAttempt] = useState(0);
  const [showReceipt, setShowReceipt] = useState(false);
  const claim = useResource<Claim>(`/claims/${id}/`, organizationId, attempt);
  const record = claim.data;
  return (
    <Dialog title="Reported claim" busy={false} onClose={onClose}>
      {claim.loading ? (
        <Loading />
      ) : claim.error ? (
        <ErrorNotice
          message={claim.error}
          retry={() => setAttempt((v) => v + 1)}
        />
      ) : (
        record && (
          <>
            <p className="muted dialog-description">
              A filed channel assertion. No payment, dispute decision or
              verified balance is implied.
            </p>
            <dl className="receipt-facts">
              <div>
                <dt>Invoice · financial year</dt>
                <dd>
                  {record.invoice_number} · {record.financial_year}
                </dd>
              </div>
              <div>
                <dt>Invoice date</dt>
                <dd>{dateOnly(record.invoice_date)}</dd>
              </div>
              <div>
                <dt>Channel</dt>
                <dd>{record.channel_name}</dd>
              </div>
              <div>
                <dt>Agency / client</dt>
                <dd>
                  {record.agency_name}
                  <br />
                  {record.client_name}
                </dd>
              </div>
              <div>
                <dt>Principal · PKR</dt>
                <dd>{amount(record.principal_amount)}</dd>
              </div>
              <div>
                <dt>GST · PKR</dt>
                <dd>{amount(record.gst_amount)}</dd>
              </div>
              <div>
                <dt>Original total · PKR</dt>
                <dd>{amount(record.invoice_total)}</dd>
              </div>
              <div>
                <dt>Reported due · PKR</dt>
                <dd>{amount(record.reported_due)}</dd>
              </div>
              <div>
                <dt>Cycle</dt>
                <dd>{record.cycle_code}</dd>
              </div>
              <div>
                <dt>Filed · PKT</dt>
                <dd>{dateTime(record.submitted_at)}</dd>
              </div>
              {record.balance_explanation && (
                <div className="wide-field">
                  <dt>Channel explanation of reduced amount</dt>
                  <dd>{record.balance_explanation}</dd>
                </div>
              )}
              <div className="wide-field">
                <dt>Claim reference</dt>
                <dd className="mono">{record.id}</dd>
              </div>
            </dl>
            <ClaimResponses
              claim={record}
              membership={membership}
              userId={userId}
              onChanged={() => {
                setAttempt((value) => value + 1);
                onChanged();
              }}
              onDraftPrepared={onChanged}
            />
            {canViewReceipt && (
              <button
                className="text-button"
                onClick={() => setShowReceipt((value) => !value)}
              >
                {showReceipt ? "Hide filing receipt" : "View filing receipt ↗"}
              </button>
            )}
            {showReceipt && (
              <Receipt
                id={record.submission_id}
                organizationId={organizationId}
              />
            )}
          </>
        )
      )}
    </Dialog>
  );
}

function ClaimBreakdown({
  group,
  filters,
  organizationId,
  revision,
  refresh,
}: {
  group: string;
  filters: string;
  organizationId: string;
  revision: number;
  refresh: () => void;
}) {
  const [page, setPage] = useState(1);
  const data = useResource<Page<ClaimGroup>>(
    `/claims/breakdown/?group_by=${group}&${filters}&page=${page}`,
    organizationId,
    revision,
  );
  if (data.loading) return <Loading />;
  if (data.error) return <ErrorNotice message={data.error} retry={refresh} />;
  if (!data.data?.results.length)
    return (
      <Empty title="No grouped reports">
        No filed claims match this scope and search.
      </Empty>
    );
  return (
    <>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={`Claims grouped by ${group}`}
      >
        <table>
          <caption className="sr-only">
            Scoped grouped claim and objection totals
          </caption>
          <thead>
            <tr>
              <th>
                {group === "channel"
                  ? "Channel"
                  : group === "client"
                    ? "Client"
                    : "Cycle"}
              </th>
              <th>Claims</th>
              <th className="numeric">Reported · PKR</th>
              <th>Open objections</th>
              <th className="numeric">Disputed · PKR</th>
            </tr>
          </thead>
          <tbody>
            {data.data.results.map((record) => (
              <tr key={record.group_id}>
                <td>
                  <strong>{record.group_name}</strong>
                </td>
                <td>{record.claim_count}</td>
                <td className="numeric">{amount(record.reported_due_total)}</td>
                <td>{record.active_objection_count}</td>
                <td className="numeric">
                  {amount(record.disputed_amount_total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager
        count={data.data.count}
        page={page}
        hasNext={!!data.data.next}
        setPage={setPage}
      />
    </>
  );
}
