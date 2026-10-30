# ADR 0001: Modular monolith with explicit business authority

Status: accepted for implementation, 30 October 2026.

The system combines interdependent claims, finance, calendar, committee and appointment records. Correct transaction boundaries and one understandable authorization model matter more than separate deployable services at the proposed workload.

Use Django/DRF and PostgreSQL, with modules owning services/selectors. React uses same-origin authenticated APIs. Business mutations and related audit/outbox records commit together. Async adapters are consumers of durable work; they do not become the authoritative ledger or deadline store.

Alternatives: independent microservices would add distributed consistency and operating cost without demonstrated need. A dashboard with direct table CRUD would make financial/authority controls bypassable. An autonomous-agent workflow would give untrusted text inappropriate authority.

Consequences: test cross-module contracts and scoped selectors; keep views/jobs thin. Add a service boundary only when measured scaling, isolation or separate ownership justifies it. Introduce queues/providers when an actual delivered workflow needs them. Do not add empty modules to imply finished scope.

Audit history is append-only for the runtime role, with separate retention/export work before production. Database-administrator tampering is outside that claim. Production policy approval, MFA and independent finance/security acceptance remain explicit gates.
