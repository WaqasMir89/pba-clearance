# PBA Clearance Platform

An independently developed clearance and agency relationship application by **WaqasMir89**. This is a work in progress, not an official PBA service or an approved interpretation of PBA policy.

The application is being delivered in small, tested steps. It will keep reported claims, verified settlement, custody, committee authority, client appointments and public status as separate records. AI will assist with documents and drafts; it will not approve payments or enforcement.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the sequence, [discovery register](docs/discovery-register.md) for external dependencies, and [progress](docs/progress.md) for actual verification evidence.

## Current scope

The delivery includes named sessions, scoped organization/client registers, audit history, candidate policy/calendar snapshots and a connected React workspace. Sandbox complaint intake supports CSV upload/review, duplicate detection, approver filing, recoverable commands and verified receipt downloads. Agencies can read only their own filed reported claims. All seeded examples are fictional. Production filing, enforcement and outbound communications remain disabled.

The S05 API adds private agency objection drafts, approver-signed versions, withdrawal/reopening, supplementary evidence statements and scoped grouped reports. Its connected browser workflow is being built next. Objections and evidence statements have no payment, clearance or enforcement effect; financial-ledger figures remain unknown.

## Development

Requires Python 3.13, uv, Docker/Compose and Node 22.12+. The foundation uses Django 5.2 LTS, DRF and PostgreSQL 18; exact dependencies are in `uv.lock`.

```sh
cp .env.example .env
docker compose up -d db
uv sync --locked
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8046
```

The dedicated development database listens on loopback port 55463. On first initialization, Compose creates a `clearance_app` database owner without superuser or BYPASSRLS privileges. `CREATEDB` is for test database creation only; production uses separate migration/runtime roles. Choose unique secrets before any shared environment. Do not reuse a pre-existing PostgreSQL volume from another product.

```sh
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run pytest
```

Liveness: `/health/live/`. Database readiness: `/health/ready/`. API schema: `/api/v1/schema/` (authenticated). Business responses are private and noncacheable. The foundation records outbox intents but does not dispatch email or any other external effect.

Provision fictional local records with `uv run python manage.py seed_demo`. In an interactive terminal it prompts for a password; automation can supply `CLEARANCE_DEMO_PASSWORD`. There is no preset password. Demo users are `demo.pba` (registry officer), `demo.channel` (two channel workspaces), `demo.approver` (sandbox filing for those channels), `demo.agency` (two agency workspaces), `demo.agencyapprover` (sandbox agency signing), `demo.reviewer` (read-only PBA auditor) and `demo.policy` (candidate policy preparation only). Re-running preserves passwords, revocations and existing records. Demo provisioning is disabled outside development.

In a second terminal:

```sh
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:5196. Vite proxies the same-origin API to Django on 8046; no cross-origin authentication setup is needed. `npm run build` checks TypeScript and builds the browser bundle; `npm run format:check` checks formatting. Development uses Node 22.12+; CI verifies Node 24. The current cycle/participant pickers expose up to 100 records; complete archive selection and production-scale workflows are later slices. Calendar creation is available through the API; the current browser calendar is read-only.

The candidate source text is in `examples/candidate-policy.txt`; its SHA-256 is reproducible. Explicit dates/times in demo data are fictional examples, not an implementation of the supplied workflow's disputed dates. Policy version and sealed calendar history are protected against application UPDATE/DELETE; milestones cannot be appended after sealing. There is no production policy approval endpoint.

The [intake contract](docs/plans/complaint-intake.md) describes CSV fields, limits, exact decimal amounts, review outcomes and response-loss recovery. Sandbox filing requires an explicit simulation timestamp inside the selected candidate window; it also records the real server time. A filed reported amount is an unverified channel assertion, not a settlement or an established outstanding balance. Corrections use new imports; sealed history cannot be edited or extended. Production policy, evidence storage and MFA remain release gates.

Follow the [fictional CSV walkthrough](examples/intake/README.md) to exercise mixed-row review, corrected upload and separate agency visibility. The browser saves pending command metadata in session storage, checks protected records after a lost response and retains the original UUID/payload for an explicit retry. Source file bytes stay in memory; after reloading an unresolved upload, reselect the unchanged CSV. Closing the tab may remove this local recovery metadata; server records and idempotency remain authoritative.

The [agency-response contract](docs/plans/agency-disputes.md) defines draft privacy, signed versions and late evidence. `examples/candidate-response-window.txt` supplies explicit fictional response instants independently of the sealed complaint calendar. Evidence is currently a bounded plain-text statement with an unverified reference; original-document storage and policy decisions remain release gates.

Authentication flow: `GET /api/v1/auth/csrf/`, then JSON `POST /api/v1/auth/login/` with `X-CSRFToken`; use `/auth/session/` for current memberships. Login rotates the CSRF token. Refresh it before subsequent JSON commands. Workspace requests require `X-Organization-ID` for a live membership. JSON `POST /auth/logout/` also requires CSRF. Only an explicitly authorized PBA registry officer can create organization/client entries, and writes are currently disabled outside development. Client visibility grants do not establish approved agency appointments or business eligibility.

MFA, shared-process rate limiting, recovery/delegation administration and production identity acceptance are still open gates. The current local login throttle uses Django's process-local cache. No Django admin bypass is exposed.

Stop the local database with `docker compose stop db`; keep the volume to preserve development records. For production, the missing release gates in the build plan still apply.

## Publication boundaries

This public repository contains application code and sanitized engineering documentation. Original discovery documents, commercial negotiations, credentials, customer data and private attachments are excluded. Public visibility does not establish a PBA endorsement or grant an open-source licence to commercial material.
