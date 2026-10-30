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

Registry writes and demo provisioning are disabled outside development. MFA, production account recovery/delegation administration, shared rate limiting and production authority acceptance remain open. No public admin or membership-management bypass is exposed. S03–S12 are not complete.
