# Implementation plan

Prepared 30 October 2026. Implementation is authorized; delivery proceeds through verified commits on `main`. The original supplied engineering plan remains the overall scope reference. This document translates it into executable delivery steps without publishing private discovery/commercial files.

Current delivery: S00–S03 and S04 sandbox intake/API/browser implemented with verification. See `docs/progress.md` and per-commit GitHub Actions for evidence. S04 production rule/evidence/identity acceptance and S05–S12 remain. The source repository is public; no production deployment or PBA acceptance is claimed.

## Evidence and decisions

The workspace initially contained an 806-line engineering plan, a 375-line private commercial proposal, an ODT departmental workflow and an empty text companion. All substantive documents were read, including extraction of all 13 ODT paragraphs. No application, legacy export, provider credentials, approved policy register or production data was supplied. The original plan references an older filename for the ODT; the file actually supplied is the workflow document in this workspace.

The original plan describes a full institutional system, not a dashboard project. It also explicitly identifies conflicts in deadlines, credit clocks, settlement routes, restoration charges and authority. Those conflicts are external discovery gates. Engineering can proceed with fictional records and candidate configuration; it cannot confer policy approval.

### Architecture

- Modular Django monolith with services for commands and selectors for scoped reads. API, management commands and later jobs use the same business boundaries.
- PostgreSQL is authoritative. The initial application will not substitute SQLite for PostgreSQL verification.
- React/TypeScript with Vite; same-origin session authentication through a development proxy, CSRF protection and explicit organization selection.
- Named users and time-bounded organization memberships. Staff/superuser status does not itself grant business-data access. No public signup or default password.
- Append-only application audit records and transactional outbox records. Database controls will prevent ordinary runtime updates/deletes to audit events; they do not protect against a database administrator. Retention-protected exports remain a release gate.
- Policy and calendar versions retain provenance. A candidate is not an approved production rule. No fixed day-of-month enforcement logic.
- Exact decimal PKR amounts. A reported claim, evidence upload, settlement, physical instrument and cash receipt are different facts.
- Add Celery/RabbitMQ, private evidence storage and provider adapters when an executable slice requires them, with durable database scheduling and reconciliation. No infrastructure is a placeholder claim of integration.

Technical support/compatibility references checked at kickoff: [Django releases](https://www.djangoproject.com/download/), [DRF requirements](https://www.django-rest-framework.org/#requirements), [PostgreSQL support](https://www.postgresql.org/support/versioning/) and [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/). Lockfiles and executed checks establish the versions actually used.

### Core invariants

1. Organization scope is checked on every read and command, including list, detail, audit and future download/export paths.
2. Business permissions come from a live, unexpired membership, never an arbitrary client-provided role.
3. An accepted command writes business state, audit and any outbox event atomically.
4. Posted evidence/history changes through linked corrections, not destructive edits.
5. Production adverse actions require approved policy, calendar, evidence and a valid authority chain. All are disabled in the initial slice.
6. Uploaded payment evidence never changes balances by itself; allocations require authoritative verification and concurrency controls.
7. Appointments/restrictions have explicit scope; releasing one ground cannot remove another.
8. Unknown or stale eligibility must not be presented as allowed.

## Requirements and acceptance map

| ID | Observable requirement | Delivery | Verification |
| --- | --- | --- | --- |
| R01 | Reproducible local service and CI against PostgreSQL | S01 | Fresh migration, readiness, lint and CI |
| R02 | Named sessions, CSRF, live scoped memberships | S02 | Anonymous/foreign/expired/revoked membership tests; login/logout |
| R03 | Scoped organization/client registry and history | S02 | Authorized API reads, command audit and negative access checks |
| R04 | Durable, append-only audit and transactional event writes | S01–S02 | Transaction rollback and database mutation rejection |
| R05 | Source-linked candidate policy and explicit calendar instants | S03 | Version/provenance/time validation and no enforcement |
| R06 | Accessible, connected operational workspace | S03 | Build, real browser flows, keyboard and responsive checks |
| R07 | Validated complaint import and immutable submission receipt | S04 | Original scenarios A01–A03, A08, A22–A23 |
| R08 | Agency review and disputes with distinct financial effect | S05 | Cross-party access, stale version and dispute invariants |
| R09 | Custody, verified settlement, allocations and reversals | S06 | A04–A07, A24; property/concurrent PostgreSQL tests |
| R10 | Immutable committee evidence and exact notice approval | S07 | A09–A11; quorum, hash, timeout and authority tests |
| R11 | Scoped restrictions, restoration and monotonic projection | S08 | A12–A13, A17; independent grounds and stale retries |
| R12 | Appointments, transfers, NOCs and mediation | S09 | A14–A16; exclusive scope concurrency |
| R13 | Authenticated correspondence and recoverable adapters | S07–S10 | A10, A17, A20; provider fault/reconciliation evidence |
| R14 | Bounded AI drafts with permission-filtered retrieval | S11 | A18–A20; consented evaluation, abstention and budget fallback |
| R15 | Reconciled migration, recovery and operational transition | S12 | A21; two rehearsals, three real monthly shadow cycles |

The original plan's A01–A24 remain required; references above describe future checks, not passed results.

## Delivery steps

### S00 — Inspection and public delivery baseline

Outcome: a source-grounded implementation sequence, explicit external gates and safe publication boundaries.

Changes: this plan, README, discovery register, architecture decision, progress record and ignore rules. Keep all original supplied documents intact and local. Use the authenticated `WaqasMir89` GitHub identity for a new public `pba-clearance` repository.

Verification/exit: inspect the exact staged tree for private documents/secrets before the first push; verify remote ownership, visibility and commit. No application readiness is implied.

Recovery: correct documentation with a new commit; never publish confidential source material to make the repository self-contained.

### S01 — Executable foundation

Outcome: Django/DRF starts, PostgreSQL migrates, health checks work, audits have database mutation protection and CI checks a clean checkout.

Changes: configuration, custom user before first migration, common IDs/errors, audit/outbox tables, locked dependencies, local PostgreSQL instructions and GitHub Actions. Database-readiness returns unavailable when its dependency fails; liveness does not leak configuration.

Dependencies: S00; available Python/PostgreSQL. Failure/recovery: fail startup on missing production secrets or unsupported database configuration; migrations are additive. No live business data exists. Do not restore real financial state by blindly reversing future migrations.

Verification: lint/format, PostgreSQL migrations, request-ID/error checks, audit update/delete rejection, transaction rollback, migration drift and CI. Exit when evidence is recorded and this step is pushed.

### S02 — Named identity and scoped registry

Outcome: provisioned users sign in, choose their organization and read only their permitted registry. An authorized registry command creates records with audit/outbox in one transaction.

Changes: memberships with role/type consistency, expiry and revocation; session/CSRF APIs; scoped selectors; organization and client services; read-only administrative views; an explicit fictional-demo command requiring an operator-provided password. No default production credentials.

Dependencies: S01. MFA, approval enrolment and recovery are required before privileged production use; this initial slice supports local development only.

Failure/recovery: reject missing/expired/foreign membership and inactive users; re-read live authorization on every request. Denials are recorded without exposing the target record. Failed multi-record commands roll back with their audit/outbox. Deactivation/revocation takes effect on the next request.

Verification: authenticated/anonymous and role/scope matrix, CSRF login/logout, foreign IDs, same-name/duplicate identifiers, invalid record creation and rollback. Test with a non-superuser, non-BYPASSRLS PostgreSQL role; RLS is not claimed in this slice.

Exit: functional scoped API, documented provisioning and passed checks pushed separately.

### S03 — Connected workspace and candidate configuration

Outcome: browser users can sign in, change workspaces, browse scoped registry/audit and inspect candidate policy/calendar records. Show empty, loading, error and permission states honestly.

Changes: typed React client, restrained table-first UI, organization selector, policy/calendar data model with source digest/reference and explicit local/UTC cutoffs. Candidate data has no enforcement effect. Preserve prior versions; no public approval endpoint yet.

Visual thesis: a calm ivory-and-ink administrative workspace with a single green accent and strong tabular hierarchy. Content plan: workspace navigation, scoped records, provenance detail and primary action. Interaction thesis: brief workspace transitions, clear row/keyboard focus and responsive navigation; respect reduced motion.

Dependencies: S02; approved policies are not required to browse fictional candidates. Production policy approval is a later gate and cannot be simulated by a developer checkbox.

Failure/recovery: clear organization data on scope changes; discard stale responses; show failed reads and allow retry. Missing calendars and policies remain explicit unknowns. Preserve drafts and do not invent deadlines.

Verification: typecheck/build, browser login/logout/switch/permission/empty/error flows, 360px and desktop geometry, console errors and focused accessibility checks. Exit: connected UI and candidate configuration tested and pushed; production acceptance remains open.

### S04 — Channel complaint intake

Detailed delivery contract: [sandbox intake plan](docs/plans/complaint-intake.md). Deliver and verify the API and connected browser as separate commits. Production filing remains disabled until the external dependencies below are resolved.

Outcome: channel stages CSV rows with exact decimals, row-level errors and duplicate candidates, then submits a frozen version with content-hashed receipt. Agency sees only its reported claims.

Dependencies: R05 policy/window approval, invoice schema, canonical mappings and evidence requirements signed by the policy owner. Sandbox can demonstrate candidate rules with clear labels.

Failure/recovery: malformed dates/decimals and mismatching totals do not enter authoritative records; natural duplicates use channel+agency+normalized number+financial year. Idempotency keys bind request hash and aggregate version. Corrected upload preserves accepted-row identities. Database uniqueness/concurrency checks prevent duplicate obligations.

Verification/exit: A01–A03/A08/A22–A23 on PostgreSQL, immutable receipt replay and channel-to-agency browser journey. Push only the verified slice; no settlement is asserted.

### S05 — Agency response and dispute intake

Outcome: scoped agency workspace, invoice-linked objections and late evidence route. Separate claimed, disputed, accepted credits and verified settlement figures.

Dependencies: S04; approved dispute effect, declaration and authorized attestation routes. Failure/recovery: dispute never becomes a payment; conflicting corrections require explicit versions/review. Verify party-specific visibility, evidence access, closed-window behavior and audit history before pushing.

### S06 — Verified settlement and physical custody

Outcome: distinct claim and cash/custody ledgers, instrument-specific transitions, maker/checker authorization, exact allocations, linked reversals and unapplied value.

Dependencies: finance-approved chart/recognition rules, bank format and beneficiary authority. Failure/recovery: lock available value and obligations, reject over-allocation; preserve unknown bank outcomes for reconciliation. No bank initiation in the baseline. Verification: A04–A07/A24, monetary conservation/property tests, simultaneous allocation races and nonprivileged PostgreSQL evidence. Financial/security review is an additional release gate.

### S07 — Committee, notices and correspondence

Outcome: immutable committee snapshots, quorum/conflicts, approvals bound to versions and final document hash, signed service evidence and durable notification outbox.

Dependencies: S05–S06, named signatories, templates, approved clock trigger and provider contracts. Introduce Celery/RabbitMQ and private evidence storage here or earlier when required. Failure/recovery: database deadlines survive queue loss; retries re-read payment/holds and invalidate stale approvals; uncertain delivery is reconciled before a sensitive resend. Verify A09–A11/A20, worker crashes and duplicate events.

### S08 — Scoped enforcement and restoration

Outcome: authorized restrictions/permissions with independent grounds, expiry and restoration; sanitized public projection with monotonic versions and eligibility `unknown` for missing/stale data.

Dependencies: S07 and signed resolution of all applicable authority/calendar/fee conflicts. Failure/recovery: separate pause switches, immediate eligibility recheck, per-ground release and projection reconciliation. Verify A12–A13/A17 and authority-negative tests. Live publication requires actual website adapter evidence and owner approval.

### S09 — Client appointments and transfers

Outcome: legal client/product registry, nonoverlapping exclusive appointments, channel-response snapshots, explicit NOC outcomes, mediation and authorized transfer effectivity.

Dependencies: S03 registry, approved scope/deadline/silence/override rules and identity evidence. Failure/recovery: no response never implies consent; concurrent transfers cannot create overlapping exclusive scope. Verify A14–A16 and approved partial-scope transfer/restriction interactions before pushing.

### S10 — Integrations and operational reconciliation

Outcome: one authorized legacy route, bank-statement format, inbound mailbox, outbound provider and website adapter; authenticated events with replay protection, bounded retries and exception queues.

Dependencies: documented interfaces and PBA-controlled credentials. Fakes prove adapter behavior only. Verify sandbox/provider callbacks and unknown-outcome reconciliation individually. Missing access blocks its adapter, not unrelated development.

### S11 — AI assistance and reporting

Outcome: optional extraction/summaries/triage restricted to suggestions, with source references, budgets, review and manual fallback. Retrieval is filtered before the AI sees data.

Dependencies: consented/redacted gold dataset, approved provider privacy/retention terms and evidence storage. Verify A18–A20 and the original plan's measured critical-field target. Prompt/model/schema provenance is retained. Provider outage never blocks core processing.

### S12 — Release and operational transition

Outcome: reconciled imports and opening state, trained owners, backup/restore, independent security review, shadow reconciliation and a reversible cutover boundary.

Dependencies: feature acceptance, named finance/policy/IT owners, supported integrations and retained legacy access. Two migration rehearsals and three actual monthly shadow cycles are mandatory. Verify A21, agreed capacity targets, security dispositions and original plan section 3 retirement criteria. Stop on unexplained balances, unauthorized actions, scope leakage or failed restoration. After external effects begin, forward correction/reconciliation replaces blind database rollback.

## Release boundaries and recovery

Source delivery is distinct from deployment and from PBA business acceptance. No public deployment, official emails, bank actions, actual customer imports or website publication is authorized by creating this repository. This build uses a dedicated local database and fictional demo identities.

Before production: implement and test MFA/recovery/session administration, rate limiting across processes, private uploads/malware scanning, retention exports, least-privilege runtime credentials, backup/restore, monitoring, policy approvals and owner sign-offs. No availability/capacity/AI target is a measured result until the corresponding experiment is recorded.

Scope remains the full original product. Banking/escrow, default SMS/WhatsApp statutory service, broadcaster enforcement, native mobile apps, full accreditation and digital-wing workflows remain excluded unless separately authorized. Commercial pricing is deliberately absent from this public plan.
