# Delivery evidence

This file records executed work. Planned checks live in `BUILD_PLAN.md`.

## S00 — Discovery and repository baseline

- Read the complete supplied engineering plan and private commercial document.
- Extracted and read all ODT workflow paragraphs; confirmed the text companion is empty.
- Confirmed the workspace has no application and no existing Git history.
- Confirmed GitHub authentication as `WaqasMir89` and availability of the proposed repository name.
- Saved the implementation sequence, acceptance map, architecture decision and unresolved owner dependencies.
- Original discovery documents and local graph artifacts are excluded from the public tree.

Public repository created at https://github.com/WaqasMir89/pba-clearance. Ownership and PUBLIC visibility verified through GitHub. Planning commit `6cee76b963af841d8d56b9948d7f3b6e68f1eb18` is on remote `main`, attributed to `WaqasMir89`.

The local requirements graph contains 38 nodes, 51 edges and six communities. Integrity diagnostics found no missing/dangling/collapsed edges. It remains local because it includes private source material; token usage was not exposed by the extraction tool and is explicitly unmeasured.

## S01 — Executable foundation

Implemented PostgreSQL-only configuration, custom UUID users, live/readiness probes, request IDs, JSON API errors, private response headers, bounded pagination, audit/outbox tables and PostgreSQL triggers rejecting audit UPDATE/DELETE. Added development database setup, locked Python dependencies and PostgreSQL-backed CI. There is no external-effect dispatcher yet.

Passed locally on Python 3.13.14, Django 5.2.18 and PostgreSQL 18.6:

- `pytest`: **12 passed**, including raw SQL/ORM audit mutation rejection, atomic rollback and dependency failure behavior.
- Database-role assertion: application connection is neither superuser nor BYPASSRLS.
- All initial migrations applied successfully; migration-drift check reports no changes.
- Django system check, Ruff lint/format and diff whitespace check passed.

The sandbox forbids host-created listening sockets; a dedicated Compose PostgreSQL container was used instead. The abandoned temporary host cluster contains no application data. Fresh-volume initialization creates the nonprivileged application owner. No production restore or provider verification has been performed. Remote CI status is recorded after pushing the executable step.

S01 remote CI [41032860537](https://github.com/WaqasMir89/pba-clearance/actions/runs/41032860537) passed on exact commit `bef89ae216fbf32dc74c93ebf8483285c2e60de5`.

## S02 — Identity and scoped registry

Implemented CSRF-protected session login/logout, current-membership discovery, time-bounded/revocable memberships, role/type validation, explicit organization selection, scoped list/detail reads and PBA registry commands. A staff/superuser flag grants no business access. Denials are audited after command rollback. Client visibility grants are explicitly distinct from agency appointments. Added fictional-data provisioning with operator-selected credentials, no password resets and no reactivation of revoked access.

Passed on the same PostgreSQL environment:

- **39 tests**, covering CSRF including token rotation, logout, wrong credentials, local rate limiting, foreign IDs, forged/expired/future/revoked memberships, inactive accounts/organizations, malformed role assignments, read-only auditors, nonprivileged superusers, database interval constraints, transactional command failure and idempotent demo provisioning.
- Warning-free, validated OpenAPI generation; CI now requires it.
- Migration apply/drift, Django system check and Ruff lint/format passed.

Registry writes and demo provisioning are disabled outside development. MFA, production account recovery/delegation administration, shared rate limiting and production authority acceptance remain open. No public admin or membership-management bypass is exposed.

S02 remote CI [41033787489](https://github.com/WaqasMir89/pba-clearance/actions/runs/41033787489) passed on exact commit `1eaa9fb2cc9ff766e66e1c9e83ad76280fc0eb1e`.

## S03 — Connected workspace and candidate configuration

Implemented a real React/TypeScript workspace for session login, organization switching, scoped organization/client lists, name search, registry creation, candidate policy preparation, read-only calendars and activity history. Added loading, empty, permission/error, retry and success states. Scope changes clear prior records and ignore stale requests. Sessions refresh when the window regains focus. No balances or operational results are fabricated.

Added a separate policy-preparer role, immutable source/version records, explicit local/UTC calendar milestones and atomic cycle sealing. Database guards prevent snapshot UPDATE/DELETE, adding milestones after sealing, inconsistent local/UTC instants and promoting a candidate to an approved state. New versions preserve historical references. All candidate/registry mutations are still restricted to development.

Executed verification:

- **57 PostgreSQL tests passed** on the non-superuser/non-BYPASSRLS application connection, including invalid policy intervals, immutable snapshots, sealed-cycle append rejection, exact cutoff conversion, historical version preservation, scope isolation and explicit fictional labels.
- Migration application/drift, Django system checks, warning-free OpenAPI validation and Ruff lint/format passed.
- TypeScript check, production browser build and Prettier check passed. npm audit found no vulnerabilities at verification time; this is not independent application security acceptance.
- Real Chromium journeys passed: sign-in/out and relogin across all five demo personas; organization and client creation; invalid reference rejection; empty search/recovery; simulated read failure/retry; channel/agency isolation and workspace switching; read-only auditor; policy-preparer separation; candidate creation; and preservation of the original cycle policy.
- Keyboard checks passed for login order, modal focus containment, Escape dismissal and return to the triggering button. Browser checks found and corrected contrast/landmark issues, a modern HTML pattern escape and modal focus return. No unhandled JavaScript exceptions occurred during the final role journeys.
- Final axe scans: **zero detected violations on six main screens**, the registry/policy dialogs and desktop/mobile login. This is automated local evidence, not a WCAG certification or real-device audit.
- **15 geometry checks** passed across overview/calendar/policy at 360, 390, 768, 1280 and 1440 pixels without page overflow. Login also passed at 360 and 1440. Desktop/mobile screenshots were visually inspected and remain in ignored local browser output.
- A local `pg_dump`/`pg_restore` exercise under `clearance_app` matched the checkpoint's six organizations, four clients, one policy, one cycle, five milestones and 28 audit/outbox records. The restored audit trigger rejected a raw SQL UPDATE. The temporary restore database and dump were removed. This does not establish production PITR, storage recovery or the four-hour recovery target.

The browser used the built bundle behind a loopback-only temporary Nginx preview because this managed sandbox does not allow an ordinary host Vite listener. The documented Vite proxy configuration is supplied for normal local development. CI now checks both the PostgreSQL backend and a clean Node 24 frontend install/build. Exact per-commit results are available in [GitHub Actions](https://github.com/WaqasMir89/pba-clearance/actions).

Current limits: cycle/participant pickers expose up to 100 records, browser calendar creation is not yet included (the candidate API exists), and all production financial/enforcement/provider/MFA/retention/migration/shadow-operation gates remain open. S04–S12 are not complete. The next delivery is validated complaint intake and immutable submission receipts, first in a clearly labeled sandbox while production rule approval is pending.

## S04a — Sandbox complaint intake API

Implemented the [intake contract](plans/complaint-intake.md): bounded UTF-8 CSV staging with preserved source bytes/digest, per-row feedback, exact decimal arithmetic, duplicate/collision review and corrected re-upload. Only a live fictional channel approver may file ready rows. Filing freezes a declaration, actual server time, explicit simulation time, source/candidate provenance and a canonical content-hashed JSON receipt. No reported amount establishes liability, payment or verified outstanding balance.

Staging and filing have payload-bound idempotency keys and protected recovery reads. Stale previews fail before posting. Channel locks and database uniqueness prevent competing requests from double-reporting an invoice. Agency reads include only that agency's filed claims; source reviews and full multi-agency receipts remain private to the channel, with explicit PBA oversight of submitted records. Database guards reject history mutation, late appends, mismatched source hashes and inconsistent filing counts/totals. Business writes, audit and outbox commit atomically.

Executed verification on PostgreSQL 18.6 using the non-superuser/non-BYPASSRLS application connection:

- **154 tests passed**, including malformed/oversized files, monetary precision, partial imports, corrected uploads, access/revocation, simulation-window boundaries, stale previews, replay/payload conflicts, rollback, raw SQL mutation/append rejection and three simultaneous-request scenarios with separate database connections.
- Migrations applied; no migration drift; Django checks, warning-free validated OpenAPI and Ruff lint/format passed.
- Existing TypeScript/production browser build passed. The new intake browser workflow is the next commit; no browser acceptance is claimed here.

The first full run encountered a stopped development database; restarting the existing dedicated Compose service restored verification without resetting its volume. The final suite above passed. Demo provisioning now adds a separate `demo.approver` while preserving existing passwords and revocations. Production filing, MFA, approved policy/period rules, original-document storage and retention remain open gates. XLSX and amendments to filed claims are later slices.

S04a remote CI [41069135716](https://github.com/WaqasMir89/pba-clearance/actions/runs/41069135716) passed both jobs on exact commit `b7f947bc5ef1b51c29e0e741fc70dac4890641db`.

## S04b — Connected intake and reported-claim workspace

Implemented CSV selection/template download, scoped code lookup, paginated import history, current/archived row reviews, outcome filters, approver declaration and explicit PKT simulation time. Added exact decimal-string formatting, receipt verification/download and scoped reported-claim search/detail/totals. Added three fictional CSV examples and a repeatable walkthrough. Shared dialog/table/form primitives now live outside the main application component.

Pending commands are saved before a mutation. Recovery checks protected server records; retries preserve the original UUID, preview digest, declaration and simulation time. Upload recovery stores metadata rather than CSV bytes. A confirmed receipt clears pending state even when the POST response was lost before a reload. Workspace/user boundaries clear rendered data; a reference-selector change does not retarget an existing import.

Executed local Chromium verification against PostgreSQL and the built browser bundle:

- Preparer staged the mixed North example: two ready rows, one invalid row, PKR 3,540.00 ready. Filing was absent from the preparer role. The approver's closing-boundary attempt was rejected; a valid simulation produced one receipt with two claims and one explicitly excluded source row.
- Corrected upload preserved two duplicates and filed only the third invoice, PKR 1,180.00. Studio's final three reports totalled PKR 4,720.00. Coast/Orbit's separate report totalled PKR 590.00. The database contained exactly three imports, three sealed filings, four invoices/claims and three filing audit events after the exercised retries.
- Injected response loss after committed upload and committed filing, blocked recovery reads, and reloaded the tab. Restored reads recovered the existing records. A separate pre-commit interruption preserved its command across reload; the explicit retry sent an identical UUID/payload and produced one filing. Simulated unavailable session storage sent **zero upload commands**.
- Downloaded canonical JSON independently reproduced SHA-256 `e9ba4d88f5275ba88fdb8f2248baa6e724d15c1d59924b5d9f5f335537bb9dba`. A modified download response was rejected by the browser hash check.
- Agency source-import/full-receipt reads were forbidden; a copied claim ID from the other agency was absent (404). PBA auditor oversight saw the four submitted claims; the policy preparer had neither intake nor reported-claim navigation. Claim search, empty results, simulated read failure/retry and preserved filters after refresh passed.
- A synthetic second reference option confirmed that selected-import cycle provenance/receipt stayed unchanged. This exercised browser selection behavior, not an additional approved calendar.
- Final agency-claim and upload/archived-review surfaces passed **10 geometry checks** at 360, 390, 768, 1280 and 1440 pixels. Focused axe scans found no violations on preparer review, approver error/receipt, pending recovery, desktop/mobile claims/detail and upload/archived review. Keyboard disclosures, modal containment/Escape/focus return and the existing registry dialog passed. Desktop/mobile screenshots were visually inspected; artifacts stay local.
- Browser checks found and fixed an off-screen table label that expanded mobile page width, transient cycle selection loss during refresh, and focus leaving a single-button modal. TypeScript/production build, Prettier and Ruff/diff checks passed. The UI commit is checked by both jobs in [GitHub Actions](https://github.com/WaqasMir89/pba-clearance/actions).

This is sandbox evidence using invented data and injected browser/network faults. It does not approve PBA rules, production identities, legal declarations, providers, evidence storage, device/cross-browser behavior or production operation. S05 dispute intake is the next delivery step; production filing and all later financial/enforcement effects remain disabled.

## S05a — Agency objection and supplementary-evidence API

Implemented agency-private immutable drafts, agency-approver signing, consecutive raised/amended/withdrawn/reopened history, source-linked canonical receipts, and participant-scoped supplementary evidence statements. A separately sourced fictional response window preserves the existing sealed cycle and complaint receipts. Ordinary signing is window/chronology/version checked; evidence statements and signed withdrawals remain available after ordinary closing. All effects on payment, reported due, clearance and enforcement remain none.

Added scoped current-objection annotations, exact separately disputed totals and paginated channel/client/cycle breakdowns. Unimplemented credits, verified settlement and reportable balance are null. Demo provisioning adds `demo.agencyapprover` without changing existing credentials/revocations.

Executed verification:

- **250 PostgreSQL tests passed** under the non-superuser/non-BYPASSRLS application role: the 154-test baseline plus 96 new checks. Coverage includes private draft/party scope, declarations, precision, partial disputes, explicit window/chronology boundaries, late/missing-window evidence, amendments/withdrawal/reopening, key recovery/conflicts, stale previews, rollback and raw SQL history/illegal revision rejection.
- Five simultaneous-request tests used separate PostgreSQL connections for draft, signature, competing initial submissions, withdrawal/amendment and evidence replay. Each preserved one command result or one next case version.
- Fresh test-database migration exposed missing prerequisite ordering for the new SQL helpers. Dependency metadata was corrected before publication; SQL operations and existing development records were preserved. Fresh migration, drift/system checks and warning-free validated OpenAPI passed.
- Ruff lint/format, diff checks and the existing TypeScript/production build passed. Connected S05 browser acceptance is the next commit.

This is a sandbox with plain-text evidence statements and unverified supplied references. Original-document storage, malware/retention controls, policy-authority decisions, MFA, financial attestation, dispute decisions/appeals and operational acceptance remain open gates.

S05a remote CI [41079939434](https://github.com/WaqasMir89/pba-clearance/actions/runs/41079939434) passed both jobs on exact commit `996fe4c3c387128dd2bbb79ff7f8efcd09a649a6`.

## S05b — Connected objections, evidence and grouped reports

Implemented agency-private draft preparation/review, approver signing, amendment, withdrawal and reopening from the reported claim. Added a submitted-case register, private draft register, signed revision history, verified JSON receipt downloads, late evidence statements and exact channel/client/cycle report views. Financial figures remain explicitly unknown; reported amounts are never reduced by a dispute.

Pending response commands save their complete payload before a write, scoped by user, workspace, action and source. A register panel opens the saved source after reload. Recovery checks protected records before an explicit retry and preserves the original UUID/payload. Rejected forms retain their entered text and declaration/time values for correction. No original file or URL is retrieved.

Executed local Chromium verification against PostgreSQL and the production browser bundle:

- Agency preparer staged a private partial objection for North invoice 101; signing was absent from that role. The agency approver's exact closing-boundary attempt was rejected and retained its entered values. A valid simulation signed version 1 for PKR 240.10. Downloaded canonical JSON independently reproduced SHA-256 `f92e80decdc24bbbfeb2f4ec5733a93836cacf071610bb5b2e33f442f63b80b7`. A modified receipt response was rejected with zero downloads.
- Amendment, withdrawal, reopening and a late withdrawal retained all five signed versions for invoice 101. A second case for invoice 102 opened at PKR 50.25. The channel read signed history and added a late counterstatement; the agency added its own late statement. Neither changed the reported total.
- Injected response loss after committed draft, withdrawal and evidence commands; blocked recovery reads and reloaded the tab for draft/evidence. Restored protected reads recovered the original results. A separate signature interruption before commit survived reload; explicit retry sent an identical UUID/payload and created exactly one signed version. Simulated unavailable session storage sent **zero draft commands**.
- Other-agency case/receipt reads returned 404, with no foreign drafts or evidence listed. The channel could not read an agency-private draft. Read-only PBA auditor oversight saw both submitted cases, all retained history and both participant statements without mutation controls. The policy preparer had no objection navigation.
- Grouped channel/client/cycle figures matched exact reported and separately disputed totals. Empty search, injected register read failure/retry and over-amount validation passed. Final local state: **four private drafts, two cases, six signed revisions and two evidence statements**. The original four claims still total **PKR 5,310.00** (Studio PKR 4,720.00; Orbit PKR 590.00); only invoice 102 has an active dispute, PKR 50.25. Accepted credits, verified settlement and reportable balance remain unknown.
- **Nine geometry and targeted WCAG axe checks** passed: reported claims at 360, 390, 768, 1280 and 1440 pixels; case register and claim/evidence detail at 360 and 1440. Modal Tab/Shift+Tab containment, Escape and focus return passed. A final complete axe scan of the receipt/detail surface found zero violations. Mobile/desktop screenshots were visually inspected and remain local. No unhandled JavaScript exceptions occurred during the final role checks.
- Browser checks found and corrected rejected-input reset and a receipt button's accessible-name mismatch. Grouped pagination resets on changed search filters. TypeScript/production build, Prettier, Ruff and diff checks passed. The unchanged backend passed its **250 PostgreSQL tests** and both CI jobs on S05a; this browser commit is also checked by both jobs in [GitHub Actions](https://github.com/WaqasMir89/pba-clearance/actions).

These are fictional sandbox records and injected faults, not production authority, policy, original-document, financial, provider, device or operational acceptance. S06 verified settlement and physical custody is the next delivery step. Production effects remain disabled.
