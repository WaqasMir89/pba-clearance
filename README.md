# PBA Clearance Platform

An independently developed clearance and agency relationship application by **WaqasMir89**. This is a work in progress, not an official PBA service or an approved interpretation of PBA policy.

The application is being delivered in small, tested steps. It will keep reported claims, verified settlement, custody, committee authority, client appointments and public status as separate records. AI will assist with documents and drafts; it will not approve payments or enforcement.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the sequence, [discovery register](docs/discovery-register.md) for external dependencies, and [progress](docs/progress.md) for actual verification evidence.

## Current scope

The first delivery establishes the application, organization isolation, audit events, registry and a connected workspace. All examples must be fictional. Production enforcement and outbound communications remain disabled.

## Development

Requires Python 3.13, uv, Docker/Compose and, for the later frontend, Node 22+. The foundation uses Django 5.2 LTS, DRF and PostgreSQL 18; exact dependencies are in `uv.lock`.

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

Provision fictional local records with `uv run python manage.py seed_demo`. In an interactive terminal it prompts for a password; automation can supply `CLEARANCE_DEMO_PASSWORD`. There is no preset password. Demo users are `demo.pba` (registry officer), `demo.channel` (two channel workspaces), `demo.agency` (two agency workspaces) and `demo.reviewer` (read-only PBA auditor). Re-running preserves passwords, revocations and existing records. Demo provisioning is disabled outside development.

Authentication flow: `GET /api/v1/auth/csrf/`, then JSON `POST /api/v1/auth/login/` with `X-CSRFToken`; use `/auth/session/` for current memberships. Login rotates the CSRF token. Refresh it before subsequent JSON commands. Workspace requests require `X-Organization-ID` for a live membership. JSON `POST /auth/logout/` also requires CSRF. Only an explicitly authorized PBA registry officer can create organization/client entries, and writes are currently disabled outside development. Client visibility grants do not establish approved agency appointments or business eligibility.

MFA, shared-process rate limiting, recovery/delegation administration and production identity acceptance are still open gates. The current local login throttle uses Django's process-local cache. No Django admin bypass is exposed.

Stop the local database with `docker compose stop db`; keep the volume to preserve development records. For production, the missing release gates in the build plan still apply.

## Publication boundaries

This public repository contains application code and sanitized engineering documentation. Original discovery documents, commercial negotiations, credentials, customer data and private attachments are excluded. Public visibility does not establish a PBA endorsement or grant an open-source licence to commercial material.
