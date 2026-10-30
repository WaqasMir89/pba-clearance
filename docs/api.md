# Initial API contracts

Version: `/api/v1/`. Exact schemas are generated from the application and validated in CI. The authenticated `/schema/` endpoint serves JSON OpenAPI.

## Authentication and scope

Use same-origin session cookies. Fetch `/auth/csrf/`, then send JSON credentials to `/auth/login/` with `X-CSRFToken`. Login rotates the token; refresh it before subsequent commands. Logout is a CSRF-protected JSON POST. There is no public registration, password reset or membership-management API in this delivery.

Every workspace endpoint requires `X-Organization-ID`. The server re-reads a current membership with matching organization type, active account/organization, start/end interval and no revocation. Staff and superuser flags grant no business-data scope. A foreign workspace is rejected; a foreign object is absent from scoped detail queries.

| Role | Registry reads | Registry creation | Candidate policy reads | Candidate preparation | Audit reads |
| --- | --- | --- | --- | --- | --- |
| PBA registry officer | Organizations/clients across registry | Yes, development only | Yes | No | Own operations workspace |
| PBA auditor | Organizations/clients across registry | No | Yes | No | Own operations workspace |
| PBA policy preparer | Own organization and explicit client visibility | No | Yes | Yes, development only | No |
| Channel preparer/approver | Own organization; explicit client visibility | No | No | No | No |
| Agency preparer/approver | Own organization; explicit client visibility | No | No | No | No |

Channel approvers may file sandbox complaint imports only in development with fictional identities and a candidate calendar. Other approval capabilities remain future work. This delivery provides no financial, notice, enforcement or appointment approval commands. MFA and production provisioning/recovery are still required before privileged production use.

## Endpoints

| Method/path | Behavior |
| --- | --- |
| `GET /auth/csrf/` | Obtain a CSRF token; anonymous access allowed |
| `POST /auth/login/` | Authenticate a named user and return current memberships |
| `GET /auth/session/` | Current user, live memberships, role capabilities and environment |
| `POST /auth/logout/` | End the current session; 204 on success |
| `GET /registry/organizations/` | Scoped records; optional `q` name search |
| `POST /registry/organizations/` | Create an agency/channel entry with audit and outbox intent |
| `GET /registry/organizations/{uuid}/` | Detail from the same scoped selector |
| `GET /registry/clients/` | Clients accessible to the selected workspace; optional `q` |
| `POST /registry/clients/` | Create a legal registry entry and explicit workspace visibility grants |
| `GET /registry/clients/{uuid}/` | Scoped legal client detail |
| `GET /policies/` | PBA candidate source/version register |
| `POST /policies/` | A policy preparer records an immutable candidate version |
| `GET /cycles/` | Sealed candidates for PBA policy readers; fictional candidates for demo organizations; empty for ordinary member organizations until an approved/publication workflow exists |
| `POST /cycles/` | Policy preparer records a candidate broadcast period and explicit milestone cutoffs atomically |
| `GET /audit/` | Append-only workspace actions, actor and request reference |
| `GET /complaint-intake/options/` | Channel-only demo clients/agencies, CSV limits and declaration; up to 100 clients, optional code/name `q`, explicit `client_count`/`client_limit` |
| `GET /complaint-import-template/` | Authenticated constant CSV headers, without workspace business data |
| `GET /complaint-imports/` | Channel-only staged imports; optional `cycle_id` and `idempotency_key` |
| `POST /complaint-imports/` | Stage bounded base64-encoded CSV, preserve original bytes/hash and return row review |
| `GET /complaint-imports/{uuid}/` | Revalidated preview, or archived filing-time review after submission |
| `POST /complaint-imports/{uuid}/submit/` | Sandbox channel approver files all ready rows against expected preview digest |
| `GET /complaint-submissions/{uuid}/` | Immutable submitted receipt for originating channel/PBA registry or auditor |
| `GET /complaint-submissions/{uuid}/receipt/` | Exact canonical JSON download; SHA-256 matches receipt content hash |
| `GET /claims/`, `GET /claims/{uuid}/` | Filed reports scoped by originating channel or affected agency; PBA oversight allowed |
| `GET /claims/summary/` | Exact decimal sum of visible reported amounts, explicitly unverified; `cycle_id`/invoice-number `q` match the list |

Lists use `{count, next, previous, results}` with 50 rows by default and a maximum requested page size of 100. Reads are private and noncacheable. `X-Request-ID` is a validated UUID or a new server-generated UUID.

Errors use `{error: {code, message, fields}, request_id}`. Validation fields are retained for correction. Anonymous sessions return 401, forbidden workspaces/roles 403, and scoped missing objects 404. JSON is the supported command format; unsupported formats are rejected. Login has a development-only process-local throttle, not a distributed production abuse-control guarantee.

## Sandbox intake commands

See the [CSV contract and failure rules](plans/complaint-intake.md). Source limits are 256 KiB and 500 records; requests are capped at 1 MiB. Staging takes `cycle_id`, `source_filename`, `csv_base64` and a UUID `idempotency_key`. Invalid file structure fails the command; valid structure preserves individual rows with `ready`, `invalid`, `review` or `duplicate` feedback. Only ready rows enter a filing. No empty receipt is allowed.

Filing takes `expected_preview_hash`, `simulation_at` (ISO timestamp with explicit offset), `declaration_version`, `declaration_accepted` and a new UUID `idempotency_key`. The candidate opening is inclusive and closing exclusive in this sandbox. Live authorization uses the actual server clock. `submitted_at` is never the simulation clock.

Both commands bind the key to the exact payload in the selected channel. Matching retries return the original result with `replayed: true`; different payloads return 409. A changed review returns `stale_preview` (409). A different command on an already filed import returns `already_filed` (409). Reconcile an uncertain staging response using the protected list filtered by its key; reconcile filing using the source import's `submission_id`, then fetch the receipt. Retrying a successful filing after the simulated close returns the same receipt, subject to current authority.

Amounts are decimal strings, never JSON numbers for browser arithmetic. `reported_due` and aggregate totals describe unverified channel reports. Full staged reviews and excluded source rows remain channel-only. Agency readers receive only their own filed claims, without the multi-agency source file or full receipt. Revocation is checked on every read and replay. Sealed imports, rows, filings, invoices and claims have database mutation/late-append guards; source-byte hashes and filing counts/totals are checked before sealing. Database administrator resistance and production private storage remain separate gates.

## Data and authority boundaries

- A registry visibility grant is not an agency appointment, NOC, clearance or permission to trade. Appointment history/exclusivity is a later module.
- Demo workspace commands propagate the fictional flag to new examples. Demo provisioning never silently resets passwords or revocations.
- Policy source digests are supplied metadata, validated as SHA-256 hex. The original bytes are not uploaded or independently verified by the initial API. The bundled fictional source has an independently reproducible digest.
- Policy versions have only `candidate` state. There is no approval or activation endpoint. A new version does not change a prior cycle's reference.
- Calendar milestones require both a local date and time. `Asia/Karachi` is explicit; UTC is derived and checked by PostgreSQL. No day-of-month schedule or date-only cutoff is inferred.
- The cycle command inserts its milestones and seals the snapshot in the same transaction. Reads omit unsealed records. Database guards prevent updates/deletes and late milestone appends after sealing.
- Registry/candidate commands commit their business write, audit and outbox intent together. Failed commands leave no partial record/history. An outbox row is not a successfully delivered notification. No dispatcher is enabled in this delivery.
- Database triggers protect snapshots/audit from ordinary application mutation. Database owners/administrators can alter the database itself; retention-protected exports and separate runtime roles remain production work.

Liveness (`/health/live/`) and PostgreSQL readiness (`/health/ready/`) sit outside the versioned authenticated API. Neither returns credentials, policy content or commercial data.

## Sandbox agency objections and evidence

All writes below are development/demo only, use the actual clock for authority, require a payload-bound UUID command key and commit audit/outbox atomically. See the [S05 contract](plans/agency-disputes.md). No objection or statement changes reported due, pays a claim, establishes clearance or creates an enforcement hold.

| Method/path | Behavior |
| --- | --- |
| `GET /dispute-options/` | Supported reason categories, sandbox declarations and explicit effect/statement boundaries |
| `GET/POST /dispute-windows/` | Immutable sourced candidate response windows; only a demo PBA policy preparer may create one per cycle |
| `GET/POST /objection-drafts/` | Agency-private staged proposals; optional claim/cycle/key filters |
| `GET /objection-drafts/{uuid}/` | Original proposal and current preview/version/window checks |
| `POST /objection-drafts/{uuid}/submit/` | Agency approver signs raised/amended/reopened revision against expected preview |
| `GET /disputes/`, `GET /disputes/{uuid}/` | Submitted cases scoped to original agency/channel and PBA registry/auditor; optional claim/cycle/invoice `q` |
| `POST /disputes/{uuid}/withdraw/` | Agency approver signs a reason and expected case version; preserved history, no settlement |
| `GET /dispute-revisions/` | Submitted revision history; case/claim filters and originating agency's key/command-type recovery |
| `GET /dispute-revisions/{uuid}/`, `GET /dispute-revisions/{uuid}/receipt/` | Immutable signed revision and exact canonical JSON download/ETag hash |
| `GET/POST /claim-evidence/`, `GET /claim-evidence/{uuid}/` | Participant statements and supplied references; claim/key recovery; PBA oversight reads only |
| `GET /claims/breakdown/` | Paginated, scoped totals grouped by `channel`, `client` or `cycle`; `group_by` defaults to channel |

Stage one claim with `expected_case_version`, positive decimal-string `disputed_amount`, `reason_code`, `explanation`, `supporting_statement`, optional `source_reference` and `idempotency_key`. Corrections create new drafts. The amount cannot exceed reported due. Unsubmitted drafts never appear in a channel/PBA read.

Signing takes the draft's `expected_preview_hash`, explicit-offset `simulation_at`, current `declaration_version`, `declaration_accepted` and `idempotency_key`. Ordinary signing requires the separately sourced window (opening inclusive, closing exclusive). Missing coverage blocks it. Previous simulation chronology is preserved. Signed versions are consecutive; `stale_dispute_version` or `stale_objection_preview` is 409 and requires review/new preparation. A late withdrawal is allowed with its own signed declaration and reason; it does not clear the claim.

Supplementary evidence accepts a bounded 6,000-character `statement`, optional reference, explicit simulation time and evidence declaration/key. It remains available before/after the response window, after withdrawal and without window coverage. Timing is recorded as `before_window`, `within_window`, `late` or `window_unknown`. The actual server timestamp is separate. References are displayed as text; the service does not retrieve a URL or verify an original document.

For uncertain mutations, use protected draft/evidence lists filtered by key, or signed revisions filtered by key and `command_type=submit|withdraw`. Replays preserve the original record under current authority. Same-key payload changes are 409. A draft's `preview.submission_id` also resolves an uncertain signature. Case/claim reads remain available after the window.

Claim details now expose objection case/revision/version/state and separately disputed amount. Summary/grouped responses keep reported and disputed totals separate. `accepted_credit_total`, `verified_settlement_total` and `remaining_reportable_balance` are null because that financial truth is not implemented. Claim list/summary/breakdown accept scoped `channel_id` and `client_id` alongside cycle and invoice search. There is no reported-minus-disputed financial calculation.
