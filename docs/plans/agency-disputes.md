# S05: Sandbox agency objections and supplementary evidence

Prepared 30 October 2026. Implementation and public delivery are authorized. This extends S04 (`9f8ad58`) and does not approve policy or enable production filing.

Status: the sandbox API and connected browser workflow are implemented. Executed checks are recorded in [delivery evidence](../progress.md#s05b--connected-objections-evidence-and-grouped-reports); the [fictional walkthrough](../../examples/agency-response-walkthrough.md) exercises the delivered scope. Production release gates below remain open.

## Evidence and delivery boundary

The supplied plan sections 5, 6.3, 6.5, 7.1 and 8 require named agency signatories, invoice-linked objections with amount/reason/evidence, retained history, a late-evidence route and an explicit separation from money and enforcement. `BUILD_PLAN.md` R08/S05 and original A08/A22/A23 apply. D01–D04 and privileged MFA remain unresolved external gates.

At the start of S05, source had immutable reported claims/receipts, exact decimals, scoped sessions and candidate calendars, with no objection records, financial ledger, approved objection window, document store or adjudication authority. The five existing milestone types do not define an objection window, and sealed calendars cannot be extended. Preserve all S04 source/receipt history.

Deliver this sandbox slice in two verified commits: (1) deterministic dispute/evidence API and PostgreSQL guards, (2) connected agency/channel review, recovery and grouped reports. Production policy, financial attestation, dispute decisions/appeals, notice holds, original-document uploads and malware/retention controls remain later work. Evidence here consists of bounded plain-text statements and supplied references, explicitly unverified; a reference is not a verified original attachment.

## Sandbox contracts

- All mutations require development, current demo users/organizations, a filed demo claim and its demo agency/channel/client. Authorization uses the actual server clock. Other organizations and PBA policy/audit roles cannot make a party's objection or evidence statement.
- Agency preparers/approvers stage immutable objection drafts. Only an agency approver signs, revises, reopens or withdraws the agency's objection. Add a separate `demo.agencyapprover`; preserve existing credentials/memberships/revocations.
- A draft binds one claim, a positive exact decimal disputed amount no greater than reported due, a reason category, explanation, supporting evidence statement/reference and the expected case version. Corrections create new drafts. Unsubmitted drafts remain private to the originating agency; channel and PBA oversight read submitted revisions only.
- One immutable case identity exists per claim. Its signed revisions are append-only, consecutive and optimistic-version checked. Derive current state from the highest committed revision; do not maintain a separately editable current balance/state. Transitions are `raised`, `amended`, `withdrawn`, `reopened`. Withdrawal and reopening preserve every earlier revision.
- An immutable, separately sourced **sandbox response window** references the original sealed candidate cycle without changing it. One window per cycle in this slice; a future corrected calendar uses a new version/cycle. Only a demo policy preparer may create it. The fictional source declares opening/closing instants explicitly; no payment cutoff or statutory objection clock is reused.
- Raising, amending and reopening require an explicit simulation time inside that window: opening inclusive, closing exclusive. Simulation cannot precede the claim's filing simulation or a previous signed revision. Actual submission time is recorded separately. Missing coverage blocks ordinary objection submission. Withdrawal remains available after the window with a signed reason; it has no financial effect.
- Both parties may append supplementary evidence statements to their own filed claim at any time, including without an objection, after withdrawal, with a missing window and after ordinary closing. Store actual and explicit simulation times and classify timing as before/within/late/unknown. An evidence statement never pays a claim or changes its disputed amount. No URL is fetched and no external communication is sent.
- Every signed revision freezes the claim/source receipt, candidate window/source, actor, declaration, reason, disputed amount and canonical JSON SHA-256. Authorized participants/PBA oversight can download exact canonical receipt bytes. Draft-only details never enter another party's response.

## Concurrency, idempotency and recovery

Every mutation has a UUID key, scoped by originating organization and command type, bound to a normalized payload hash. Successful replays return their original records under current authorization even if a simulation window or case version has since changed. Reusing a key for a different payload is 409.

Lock memberships/organizations in a consistent order, then lock the claim/case while deciding a transition. PostgreSQL uniqueness and a revision insertion guard enforce one case identity and consecutive legal transitions under competing connections. The expected case version is authoritative: an old draft cannot overwrite another signed revision. Stale drafts require a newly prepared draft; a changed preview requires review before signing. Signed state, audit and outbox intent commit together; failures roll back all of them. No outbound dispatcher is enabled.

The browser stores exact pending command metadata/payload in session storage before writes, scoped by user/workspace/action. It reconciles via protected key/detail reads before any uncertain replay, keeps the same UUID/payload across reloads, and never automatically creates a replacement command. Definite rejection permits correction; unknown outcomes remain recoverable. Failure to save recovery metadata sends no command. Pending local content is not an evidence archive.

## API and presentation

Add `apps/disputes` with scoped selectors, validation/services and immutable models for windows, staged drafts, cases, revisions and evidence statements. Existing complaint amounts remain immutable. Extend reported-claim reads with current objection state and aggregate/grouped views using exact decimal strings. Accepted credits, verified settlement and remaining reportable balance are **unknown**, not zero or a computed reported-minus-disputed amount.

Proposed versioned endpoints:

- `/dispute-windows/`: visible fictional candidates; policy-preparer-only creation.
- `/objection-drafts/`, `/{id}/`, `/{id}/submit/`: agency-only staging/review/key recovery and approver signing.
- `/disputes/`, `/{id}/`, `/{id}/withdraw/`: submitted party-scoped cases/revisions and signed withdrawal.
- `/dispute-revisions/{id}/`, `/{id}/receipt/`: authorized immutable revision/recovery/download.
- `/claim-evidence/`: participant/PBA scoped reads and participant-only supplementary statements, filterable by claim/key.
- `/claims/breakdown/`: grouped, scoped, paginated channel/client/cycle totals; include separately reported disputed values and unknown financial fields.

Connect the existing reported-claim detail to draft preparation, submitted objection history and supplementary evidence. Agency approvers review the exact draft/context and declaration before signing. Add an objection register and agency-private draft register. Show stale version/window errors, late statement timing, empty/permission/read failure states, and explicit unknown financial figures. Keep the established ivory/ink/green table-based layout, shared dialogs and reduced-motion behavior.

## Verification and exit gates

Backend checks: baseline suite; amount/text/offset validation; scope/role matrix, source draft privacy, live expiry/revocation; simulation boundaries/missing window/chronology; revision/withdrawal/reopen behavior; exact totals with no settlement effect; partial disputes; idempotency conflicts/replay after closing; stale drafts; transactional outbox failure; raw SQL update/delete/illegal revision rejection; simultaneous same-key and different-key version races using independent non-superuser/non-BYPASSRLS PostgreSQL connections. Apply additive migrations, check drift, validate OpenAPI warning-free and run Ruff/required CI.

Browser checks: preparer draft handoff to agency approver; partial objection visible only to affected channel/agency/PBA; channel counter-statement; closed-window rejection with late evidence still accepted; amendment/withdrawal/reopen history; unknown-response/key recovery and exact retry; grouped reports and unchanged reported totals; keyboard/modal behavior, mobile geometry and targeted axe scans. Fixtures and injected failures establish local sandbox behavior only.

Push each verified slice and verify the exact remote commit and both CI jobs. Stop on scope leakage, duplicate revisions, lost signed history, altered claim totals, inferred payment/clearance or a receipt digest mismatch. Migrations are additive with no customer backfill. Preserve posted records and correct forward; reverting application code is not a reason to delete signed evidence.

Production release still requires policy-authority decisions on clock/effect/declaration, named authority/MFA, private original-document storage, retention, financial review, provider evidence and later operational/shadow acceptance. This slice does not manufacture those approvals.
