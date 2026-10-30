import { useState } from "react";
import { api, ApiError } from "./api";
import { ErrorNotice, FormError, Loading } from "./components";
import { amount, dateTime } from "./format";
import { useResource } from "./hooks";
import { downloadText, sha256 } from "./intakeCommands";
import type { Submission } from "./types";

export function Receipt({
  id,
  organizationId,
}: {
  id: string;
  organizationId: string;
}) {
  const [attempt, setAttempt] = useState(0);
  const receipt = useResource<Submission>(
    `/complaint-submissions/${id}/`,
    organizationId,
    attempt,
  );
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function download() {
    if (!receipt.data || downloading) return;
    setDownloading(true);
    setError(null);
    setDownloaded(false);
    try {
      const content = await api<string>(
        `/complaint-submissions/${id}/receipt/`,
        {
          organizationId,
          responseType: "text",
        },
      );
      const hash = await sha256(new TextEncoder().encode(content));
      if (hash !== receipt.data.content_hash)
        throw new ApiError(
          0,
          "The receipt hash does not match. Download stopped; request an integrity review.",
        );
      downloadText(
        content,
        `complaint-receipt-${id}.json`,
        "application/json;charset=utf-8",
      );
      setDownloaded(true);
    } catch (error) {
      setError(error);
    } finally {
      setDownloading(false);
    }
  }
  if (receipt.loading) return <Loading />;
  if (receipt.error)
    return (
      <ErrorNotice
        message={receipt.error}
        retry={() => setAttempt((v) => v + 1)}
      />
    );
  const record = receipt.data!;
  return (
    <section className="receipt-panel" aria-label="Filing receipt">
      <div className="section-heading">
        <div>
          <p className="eyebrow">SANDBOX FILING RECEIPT</p>
          <h2>Filing recorded</h2>
          <p>
            Immutable reported claims. Settlement and liability remain
            unverified.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={download}
          disabled={downloading}
        >
          {downloading ? "Verifying receipt…" : "Verify & download receipt"}
        </button>
      </div>
      {downloaded && (
        <p className="success-notice" role="status">
          SHA-256 verified. Receipt download started.
        </p>
      )}
      <FormError error={error} />
      <dl className="receipt-facts">
        <div>
          <dt>Receipt reference</dt>
          <dd className="mono">{record.id}</dd>
        </div>
        <div>
          <dt>Channel</dt>
          <dd>{record.receipt.channel.legal_name}</dd>
        </div>
        <div>
          <dt>Filed rows · reported amount</dt>
          <dd>
            {record.row_count} · PKR {amount(record.reported_total)}
          </dd>
        </div>
        <div>
          <dt>Signed by</dt>
          <dd>{record.submitted_by}</dd>
        </div>
        <div>
          <dt>Actual submission · PKT</dt>
          <dd>{dateTime(record.submitted_at)}</dd>
        </div>
        <div>
          <dt>Simulation time · PKT</dt>
          <dd>{dateTime(record.simulation_at)}</dd>
        </div>
        <div>
          <dt>Cycle · candidate source</dt>
          <dd>
            {record.receipt.cycle.code}
            <br />
            {record.receipt.policy.code} · v{record.receipt.policy.version}
          </dd>
        </div>
        <div>
          <dt>Source file</dt>
          <dd>{record.receipt.source.filename}</dd>
        </div>
        <div className="wide-field">
          <dt>Receipt SHA-256</dt>
          <dd className="digest">{record.content_hash}</dd>
        </div>
        <div className="wide-field">
          <dt>Original CSV SHA-256</dt>
          <dd className="digest">{record.receipt.source.sha256}</dd>
        </div>
      </dl>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Filed receipt rows"
      >
        <table>
          <caption className="sr-only">Rows included in this filing</caption>
          <thead>
            <tr>
              <th>Source row</th>
              <th>Invoice</th>
              <th>Agency / client</th>
              <th className="numeric">Reported due · PKR</th>
            </tr>
          </thead>
          <tbody>
            {record.receipt.rows.map((row) => (
              <tr key={String(row.invoice_id)}>
                <td>{row.source_row_number}</td>
                <td>
                  <strong>{row.invoice_number}</strong>
                  <span className="subject-reference">
                    {row.financial_year}
                  </span>
                </td>
                <td>
                  {row.agency_name}
                  <span className="subject-reference">{row.client_name}</span>
                </td>
                <td className="numeric">{amount(String(row.reported_due))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {record.receipt.excluded_rows.length > 0 && (
        <p className="muted small-copy">
          Excluded source rows:{" "}
          {record.receipt.excluded_rows
            .map((row) => `${row.number} (${row.status})`)
            .join(", ")}
          . Correct these in a new import.
        </p>
      )}
      <details className="intake-help">
        <summary>Accepted declaration</summary>
        <p className="muted">{record.receipt.declaration.text}</p>
      </details>
    </section>
  );
}
