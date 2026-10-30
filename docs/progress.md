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
