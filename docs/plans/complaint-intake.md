# S04: Sandbox complaint intake and immutable filing receipts

Status: implementation authorized; prepared 30 October 2026. This adds the next usable slice after commit `760b34e`. It does not approve policy or enable production filing.

## Evidence and scope

The supplied plan, section 6.2, requires invoice/client/agency fields, exact monetary validation, duplicate detection, corrected re-upload, a declaration and an immutable submission receipt. Sections 5 and 8 require named approvers, scoped reads, separate financial truth and preserved history. Acceptance scenarios A01–A03, A08, A22 and A23 apply here.

The current application has live memberships, explicit client visibility grants, protected audit/outbox writes, immutable candidate policies and sealed calendar snapshots. It has no approved policy, MFA, original-document store, settlement ledger or complaint tables. Client visibility is not an approved agency appointment. Those boundaries remain explicit.

Deliver CSV intake first. XLSX, signed production invoice/financial-year interpretations, private attachment uploads, amendments to already filed claims, disputes and financial settlement remain later work. Read access will stay available after the simulated filing window closes.

## Sandbox and authority

- Writes require `development`, a current demo user, an active demo channel and a sealed demo cycle/policy. Every agency and client must also be an explicit demo record with the client shared with both parties.
- Channel preparers and channel approvers may stage an import. Only a channel approver may file it. Provision a separate fictional approver account; do not elevate existing preparers or reset existing credentials.
- Filing uses an explicit **simulation time** to exercise the existing fictional calendar. Its opening is inclusive and closing is exclusive for this sandbox only. The receipt separately records the real server submission time. No timestamp is backdated and no date-only cutoff is invented.
- No real notice, clearance, payment, settlement or enforcement action results. The receipt attests a fictional report, not verified liability or funds.

## CSV contract and feedback

UTF-8 (optional BOM), comma-delimited CSV; at most 256 KiB and 500 data records per import. The raw source bytes and SHA-256 are preserved privately in PostgreSQL for this bounded development slice. No file content enters Git or a public URL. Production evidence storage remains a separate release gate.

Required headers: `agency_code`, `client_code`, `financial_year`, `invoice_number`, `invoice_date`, `broadcast_start`, `broadcast_end`, `principal_amount`, `gst_amount`, `invoice_total`, `reported_due`, `currency`, `delivery_reference`.

Optional headers: `invoice_delivered_on`, `release_order_reference`, `source_id`, `balance_explanation`.

Headers are trimmed and case-normalized; duplicate, missing and unknown headers fail explicitly. Incorrect field counts, invalid dates/decimals/totals or inaccessible identities receive row-level feedback. A missing delivery reference, an unexplained reduction from original total or an ambiguous invoice identity requires review; it cannot be silently filed. No statutory credit clock, tax rate, fee or surcharge is assumed.

Amounts are ASCII decimal strings with at most two fractional places and sixteen integer digits; no binary floats, exponent notation, grouping separators, NaN or negative posting. Principal + GST must equal original total. Reported due must be positive and no greater than the total. Prior reductions need a source explanation and remain unverified channel assertions.

Dates use ISO `YYYY-MM-DD`. Broadcast dates must be ordered and fall within the selected broadcast period. Unusual invoice/delivery ordering is surfaced rather than silently corrected. Simulation filing cannot precede the invoice.

`financial_year` is an explicit consecutive-year source label (`YYYY-YYYY`), not an inferred Pakistani tax-period rule. Reuse of an existing invoice number under another year or changed facts is flagged for identity review. Production period boundaries require D02/D03 resolution.

Preserve the original invoice number. The exact identity normalizes Unicode compatibility/case/whitespace, keeping separators, and combines channel, agency, financial-year label and normalized number. A separator-insensitive comparison key flags possible collisions; it never silently merges them. Identical existing reports are duplicates; changed financial/client/date facts require review. Cross-channel invoice numbers remain independent. Conflicting rows within one file are all flagged; exact repeated rows are counted once.

## Records and commands

New module: `apps/complaints`, with shared deterministic parsing/validation, scoped selectors and transactional services.

- An import preserves source bytes/hash, channel, cycle, creator, idempotency key and immutable source rows. Row feedback is revalidated on review/filing; it is not a permanent approval.
- A preview returns statuses `ready`, `invalid`, `review`, `duplicate`, exact ready totals and a content digest. The digest excludes read timestamps and binds the actual source/context, canonical facts and current outcomes.
- A filing command takes the import ID, expected preview digest, simulation time, accepted declaration version and a UUID idempotency key. It files **all currently ready rows once**, explicitly excluding other rows. The preview must still match; stale input is a 409 requiring review.
- One import can be filed once. Corrections and any remaining rows use a new import; already filed identities become duplicates rather than new obligations. A file with no ready rows cannot create an empty receipt.
- Persist one invoice identity and one reported claim per newly filed obligation, with database uniqueness. No verified settlement or calculated outstanding balance is invented.
- A sealed filing receipt preserves signer, actual and simulated times, original source hash, cycle/policy provenance, declaration, invoice/claim IDs and decimal amounts. Its canonical UTF-8 JSON is SHA-256 hashed and available to authorized readers for download/verification.
- Immutable/sealing database guards prevent edits, deletes or late row appends. A receipt can seal only when posted line counts/totals match its declared values.
- State, audit and outbox intent commit together. Serialize competing commands for the same channel and preserve database uniqueness as the final duplicate guard. There is no external dispatcher or exactly-once delivery claim.

## Idempotency and recovery

Both staging and filing keys are scoped to the selected channel and command. A repeated key with the same payload returns the original record; reuse with different content is a 409. A successful filing replay returns the same receipt even after the simulated deadline, while still enforcing current access.

The browser retains a pending command UUID and exact filing payload across lost responses and reloads, scoped by user/workspace/import. It checks protected GET endpoints before retrying an uncertain result. Replays retain the original payload/key; it never silently changes a stale preview digest. Definite validation failures may be corrected and reviewed under a new command. Pending file content stays in memory; a staged-import key supports read-only lookup after a response loss.

## API and visibility

- `GET /complaint-intake/options/`: channel-scoped eligible demo counterparties, limits and declaration.
- `GET /complaint-import-template/`: authenticated constant CSV header template, without business data.
- `GET/POST /complaint-imports/`: channel-only staged imports; filter by cycle or staging key for recovery.
- `GET /complaint-imports/{id}/`: channel-only source review and current preview; never visible to another channel or agency.
- `POST /complaint-imports/{id}/submit/`: sandbox approver command.
- `GET /complaint-submissions/{id}/` and `/receipt/`: filing receipt/actual canonical bytes, restricted to the originating channel or explicit PBA oversight roles. Agencies never receive a multi-agency source file or full receipt.
- `GET /claims/`, `/claims/summary/` and `/claims/{id}/`: filed reported claims. A channel sees its own reports; an agency sees only claims against itself; PBA registry/auditor roles have explicit submitted-record oversight. Policy preparers and ordinary staff have no implicit access.

## Browser slice

Add separate complaint-intake and reported-claims working surfaces. Reuse shared UI primitives through a small component module rather than adding another subsystem to the existing application file. Show cycle, source digest, ready/invalid/review/duplicate counts and exact reported totals. Keep amounts as formatted decimal strings.

The approver reviews the simulated filing time and declaration before filing. A filed import becomes a read-only receipt. Show unknown-outcome recovery, explicit retry, closed-window feedback and persistent read access. Scopes clear on workspace changes. A selected import keeps its own cycle provenance if the reference selector changes; it is never silently retargeted.

## Delivery and verification gates

1. **Backend:** migrations, strict CSV validation, deduplication, scoped APIs, transactional filing, idempotency and immutable receipt guards. Verify with PostgreSQL, then commit/push and check exact CI. Existing browser behavior must continue to build.
2. **Connected UI:** upload/review/declaration/receipt recovery and agency reported-claim views; fictional examples and documentation. Verify browser flows, keyboard/responsive/error states and targeted axe scans, then commit/push and check exact CI.

Meaningful tests: malformed/over-limit CSV; nonfinite/overprecision amounts; mixed valid/invalid rows; corrected upload; case/space duplicates; conflicting and cross-year collisions; cross-channel independence; invalid party visibility; preparer versus approver; foreign import/receipt/claim reads; current revocation; window boundaries; exact decimal totals; changed preview; payload/key conflicts; response-loss replay; transactional rollback; raw SQL immutability/append attempts; simultaneous same-invoice and same-key filings with separate PostgreSQL connections.

Browser acceptance: stage a mixed fictional file as preparer, file ready rows as approver, verify/download the receipt, correct/re-upload without duplicating accepted rows, and inspect only the affected agency's reports. Exercise lost response/read-only recovery and small-screen/keyboard behavior. Fixtures and simulated network failures prove these paths only, not PBA approval, live integrations or production readiness.

Migration is additive and contains no customer import. Stop on unexplained totals, duplicate obligations, authorization leakage or a receipt that does not reproduce its digest. Preserve posted records if a later defect requires forward correction. The existing D01–D18 discovery/release gates remain authoritative for production.
