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

Approver role names reserve future capabilities; this delivery provides no financial, notice, enforcement or appointment approval commands. MFA and production provisioning/recovery are still required before privileged production use.

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

Lists use `{count, next, previous, results}` with 50 rows by default and a maximum requested page size of 100. Reads are private and noncacheable. `X-Request-ID` is a validated UUID or a new server-generated UUID.

Errors use `{error: {code, message, fields}, request_id}`. Validation fields are retained for correction. Anonymous sessions return 401, forbidden workspaces/roles 403, and scoped missing objects 404. JSON is the supported command format; unsupported formats are rejected. Login has a development-only process-local throttle, not a distributed production abuse-control guarantee.

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
