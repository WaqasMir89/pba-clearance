import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError, errorMessage } from "./api";
import { useDebounced, useResource } from "./hooks";
import { dateTime, dateOnly } from "./format";
import { ComplaintIntake } from "./ComplaintIntake";
import { ReportedClaims } from "./ReportedClaims";
import {
  Icon,
  Brand,
  ErrorNotice,
  Empty,
  Loading,
  Pager,
  Dialog,
  FormError,
} from "./components";
import type {
  AuditEvent,
  Client,
  Cycle,
  Membership,
  Organization,
  Page,
  Policy,
  Session,
} from "./types";

type Section =
  | "overview"
  | "organizations"
  | "clients"
  | "calendar"
  | "intake"
  | "claims"
  | "policies"
  | "activity";
const REFERENCE_PATTERN = "[a-zA-Z0-9_\\-]+";
const sections: { id: Section; label: string; icon: string }[] = [
  {
    id: "overview",
    label: "Overview",
    icon: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  },
  {
    id: "organizations",
    label: "Organizations",
    icon: "M3 21h18 M5 21V7l7-4 7 4v14 M9 9h1 M14 9h1 M9 13h1 M14 13h1 M10 21v-4h4v4",
  },
  {
    id: "clients",
    label: "Client registry",
    icon: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 4a4 4 0 0 1 0 7 M22 21v-2a4 4 0 0 0-3-3.87",
  },
  {
    id: "intake",
    label: "Complaint intake",
    icon: "M12 3v12 M7 8l5-5 5 5 M4 14v6h16v-6",
  },
  {
    id: "claims",
    label: "Reported claims",
    icon: "M6 3h12v18H6z M9 7h6 M9 11h6 M9 15h3",
  },
  {
    id: "calendar",
    label: "Cycle calendar",
    icon: "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2 M16 3v4 M8 3v4 M3 11h18",
  },
  {
    id: "policies",
    label: "Policy register",
    icon: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h6",
  },
  {
    id: "activity",
    label: "Activity log",
    icon: "M3 12a9 9 0 1 0 3-6 M3 3v5h5 M12 7v5l3 2",
  },
];
export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [organizationId, setOrganizationId] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setBootError("");
    api<Session>("/auth/session/", { signal: controller.signal }).then(
      (value) => {
        if (active) {
          setSession(value);
          setLoading(false);
        }
      },
      (error: unknown) => {
        if (!active) return;
        if (!(error instanceof ApiError && error.status === 401))
          setBootError(errorMessage(error));
        setLoading(false);
      },
    );
    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt]);
  useEffect(() => {
    const expired = () => {
      setSession(null);
      setOrganizationId("");
    };
    window.addEventListener("clearance-session-expired", expired);
    return () =>
      window.removeEventListener("clearance-session-expired", expired);
  }, []);
  const sessionUserId = session?.user.id;
  useEffect(() => {
    if (!sessionUserId) return;
    const controller = new AbortController();
    let active = true;
    let generation = 0;
    const refreshSession = async () => {
      const current = ++generation;
      try {
        const value = await api<Session>("/auth/session/", {
          signal: controller.signal,
        });
        if (active && generation === current) setSession(value);
      } catch (error) {
        if (active && error instanceof ApiError && error.status === 401) {
          setSession(null);
          setOrganizationId("");
        }
      }
    };
    window.addEventListener("focus", refreshSession);
    return () => {
      active = false;
      controller.abort();
      window.removeEventListener("focus", refreshSession);
    };
  }, [sessionUserId]);
  if (loading)
    return (
      <main className="boot">
        <Brand />
        <Loading />
      </main>
    );
  if (bootError)
    return (
      <main className="boot">
        <Brand />
        <ErrorNotice
          message={bootError}
          retry={() => setAttempt((v) => v + 1)}
        />
      </main>
    );
  if (!session)
    return (
      <Login
        onSignedIn={(value) => {
          setSession(value);
          setOrganizationId("");
        }}
      />
    );
  const membership =
    session.memberships.find((m) => m.organization.id === organizationId) ||
    session.memberships[0];
  return (
    <Workspace
      key={membership?.organization.id || "no-membership"}
      session={session}
      membership={membership}
      onSwitch={setOrganizationId}
      onSignedOut={() => {
        setSession(null);
        setOrganizationId("");
      }}
    />
  );
}

function Login({ onSignedIn }: { onSignedIn: (session: Session) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      onSignedIn(
        await api<Session>("/auth/login/", { body: Object.fromEntries(form) }),
      );
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-context">
        <Brand />
        <div className="login-title">
          <p className="eyebrow">CLEARANCE WORKSPACE</p>
          <h1>
            One place for
            <br />
            the complete record.
          </h1>
          <p>
            Organizations, client relationships and source-linked clearance
            records.
          </p>
          <div className="context-rule" />
          <span className="context-status">
            Development environment · Enforcement disabled
          </span>
        </div>
        <p className="login-footnote">
          Independent development by WaqasMir89
          <br />
          Not an official PBA service
        </p>
      </section>
      <section className="login-form-area">
        <div className="login-form-wrap">
          <p className="eyebrow">WORKSPACE ACCESS</p>
          <h2>Member sign in</h2>
          <p className="muted">
            Use the account provisioned for your organization.
          </p>
          <form onSubmit={submit} className="stack-form">
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                required
                maxLength={150}
                autoFocus
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                maxLength={256}
              />
            </label>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <button className="primary-button" disabled={busy}>
              {busy ? "Signing in…" : "Sign in to workspace"}
              <span aria-hidden="true">↗</span>
            </button>
          </form>
          <p className="login-help">
            Local demo accounts use the password selected during setup. Contact
            your workspace administrator for account access.
          </p>
        </div>
        <p className="version-note">
          Clearance platform <span>v0.1 · Development</span>
        </p>
      </section>
    </main>
  );
}

function Workspace({
  session,
  membership,
  onSwitch,
  onSignedOut,
}: {
  session: Session;
  membership?: Membership;
  onSwitch: (id: string) => void;
  onSignedOut: () => void;
}) {
  const [requestedSection, setSection] = useState<Section>("overview");
  const [signingOut, setSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [revision, setRevision] = useState(0);
  const [cycleId, setCycleId] = useState("");
  const organizationId = membership?.organization.id || "";
  const cycles = useResource<Page<Cycle>>(
    "/cycles/?page_size=100",
    organizationId,
    revision,
  );
  // Sealed cycle references are immutable. Keep the same selection during a refresh;
  // Workspace is remounted on organization changes, so this cache cannot cross scopes.
  const [knownCycles, setKnownCycles] = useState<Page<Cycle>>();
  useEffect(() => {
    if (cycles.data) setKnownCycles(cycles.data);
  }, [cycles.data]);
  const referenceCycles = cycles.data || knownCycles;
  const cycle =
    referenceCycles?.results.find((c) => c.id === cycleId) ||
    referenceCycles?.results[0];
  const allowedSections = sections.filter(
    (s) =>
      (s.id !== "activity" || membership?.can_view_audit) &&
      (s.id !== "policies" || membership?.can_view_policy) &&
      (s.id !== "intake" || membership?.can_stage_complaints) &&
      (s.id !== "claims" || membership?.can_view_claims),
  );
  const section = allowedSections.some((s) => s.id === requestedSection)
    ? requestedSection
    : "overview";
  const currentSection = sections.find((s) => s.id === section)!;
  async function signOut() {
    setSigningOut(true);
    setLogoutError("");
    try {
      await api("/auth/logout/", { body: {} });
      onSignedOut();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSignedOut();
      else setLogoutError(errorMessage(error));
    } finally {
      setSigningOut(false);
    }
  }
  const refresh = () => setRevision((v) => v + 1);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-content">
        Skip to workspace
      </a>
      <aside className="sidebar" aria-label="Workspace navigation panel">
        <Brand />
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Workspace navigation">
          {allowedSections.map((s) => (
            <button
              key={s.id}
              className={section === s.id ? "nav-item active" : "nav-item"}
              aria-current={section === s.id ? "page" : undefined}
              onClick={() => setSection(s.id)}
            >
              <Icon path={s.icon} />
              {s.label}
              {section === s.id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="environment-dot" />
          <div>
            {session.environment === "development"
              ? "Development"
              : "Restricted environment"}
            <small>Enforcement disabled</small>
          </div>
        </div>
        <div className="sidebar-attribution">
          Independent PBA clearance project
        </div>
      </aside>
      <div className="workspace-shell">
        <header className="topbar">
          <div className="workspace-switch">
            <label htmlFor="workspace-select">Organization workspace</label>
            <select
              id="workspace-select"
              value={organizationId}
              onChange={(e) => onSwitch(e.target.value)}
              disabled={!membership}
            >
              {session.memberships.map((m) => (
                <option key={m.id} value={m.organization.id}>
                  {m.organization.legal_name}
                </option>
              ))}
              {!membership && <option value="">No workspace assigned</option>}
            </select>
          </div>
          <div className="user-menu">
            <span className="avatar" aria-hidden="true">
              {(session.user.name || session.user.username)
                .slice(0, 1)
                .toUpperCase()}
            </span>
            <div>
              <strong>{session.user.name || session.user.username}</strong>
              <small>{membership?.role_label || "No active membership"}</small>
            </div>
            <button
              className="text-button sign-out"
              onClick={signOut}
              disabled={signingOut}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <main
          id="workspace-content"
          className="workspace-content"
          tabIndex={-1}
        >
          <div className="breadcrumb">
            Workspace <span>/</span> {currentSection.label}
          </div>
          {logoutError && <ErrorNotice message={logoutError} />}
          {!membership ? (
            <Empty title="No active workspace">
              An administrator must assign a current organization membership
              before you can view records.
            </Empty>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">
                    {membership.organization.kind === "pba"
                      ? "ASSOCIATION OPERATIONS"
                      : `${membership.organization.kind.toUpperCase()} WORKSPACE`}
                  </p>
                  <h1>
                    {section === "overview"
                      ? "Workspace overview"
                      : currentSection.label}
                  </h1>
                  <p className="muted">
                    {section === "overview"
                      ? "Your organization records and current configuration, at a glance."
                      : descriptions[section]}
                  </p>
                </div>
                <div className="cycle-switch">
                  <label htmlFor="cycle-select">REFERENCE CYCLE</label>
                  <select
                    id="cycle-select"
                    value={cycle?.id || ""}
                    onChange={(e) => setCycleId(e.target.value)}
                    disabled={!referenceCycles?.results.length}
                  >
                    {referenceCycles?.results.map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.code}
                      </option>
                    ))}
                    {!referenceCycles?.results.length && (
                      <option value="">
                        {cycles.loading
                          ? "Loading cycles…"
                          : cycles.error
                            ? "Cycles unavailable"
                            : "No candidate calendar"}
                      </option>
                    )}
                  </select>
                </div>
              </div>
              <div className="scope-note">
                <span className="status-dot" />
                <span>
                  {membership.organization.is_demo
                    ? "Fictional demonstration workspace."
                    : "Development workspace."}{" "}
                  <strong>
                    No policy or calendar here authorizes enforcement.
                  </strong>
                </span>
                <span className="scope-label">CANDIDATE ONLY</span>
              </div>
              <div className="page-body" key={section}>
                {(section === "intake" || section === "claims") &&
                  cycles.error && (
                    <ErrorNotice
                      message={`Reference calendars could not be refreshed. ${cycles.error}`}
                      retry={refresh}
                    />
                  )}
                {section === "overview" && (
                  <Overview
                    membership={membership}
                    cycle={cycle}
                    cyclesError={cycles.error}
                    cyclesLoading={cycles.loading}
                    revision={revision}
                    refresh={refresh}
                    navigate={setSection}
                  />
                )}
                {(section === "organizations" || section === "clients") && (
                  <RegistryList
                    kind={section}
                    membership={membership}
                    environment={session.environment}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
                {section === "calendar" &&
                  (cycles.loading ? (
                    <Loading />
                  ) : cycles.error ? (
                    <ErrorNotice message={cycles.error} retry={refresh} />
                  ) : (
                    <Calendar cycle={cycle} />
                  ))}
                {section === "intake" && membership.can_stage_complaints && (
                  <ComplaintIntake
                    userId={session.user.id}
                    membership={membership}
                    cycle={cycle}
                    cycles={referenceCycles?.results || []}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
                {section === "claims" && membership.can_view_claims && (
                  <ReportedClaims
                    key={cycle?.id || "all"}
                    membership={membership}
                    cycle={cycle}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
                {section === "policies" && (
                  <PolicyList
                    membership={membership}
                    environment={session.environment}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
                {section === "activity" && (
                  <Activity
                    membership={membership}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
              </div>
              <footer className="workspace-footer">
                <span>Times shown in Asia/Karachi (PKT)</span>
                <span>
                  Source delivery in progress <span aria-hidden="true">·</span>{" "}
                  v0.1
                </span>
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

const descriptions: Record<Exclude<Section, "overview">, string> = {
  intake:
    "Stage fictional invoice rows, resolve feedback and file an immutable sandbox report.",
  claims:
    "Filed channel assertions within your organization scope. Settlement remains unverified.",
  organizations:
    "Named channel and agency records within your permitted scope.",
  clients:
    "Legal client records. Visibility does not establish an approved agency appointment.",
  calendar:
    "Explicit local cutoffs, broadcast periods and their source policy version.",
  policies: "Source-linked candidate versions preserved for review.",
  activity: "Recorded workspace actions and their request references.",
};

function Overview({
  membership,
  cycle,
  cyclesError,
  cyclesLoading,
  revision,
  refresh,
  navigate,
}: {
  membership: Membership;
  cycle?: Cycle;
  cyclesError?: string;
  cyclesLoading: boolean;
  revision: number;
  refresh: () => void;
  navigate: (section: Section) => void;
}) {
  const organizations = useResource<Page<Organization>>(
    "/registry/organizations/?page_size=8",
    membership.organization.id,
    revision,
  );
  const clients = useResource<Page<Client>>(
    "/registry/clients/?page_size=1",
    membership.organization.id,
    revision,
  );
  return (
    <>
      <div className="metrics">
        <div>
          <span>Visible organizations</span>
          <strong>{organizations.data?.count ?? "—"}</strong>
          <small>Within your workspace scope</small>
        </div>
        <div>
          <span>Client records</span>
          <strong>{clients.data?.count ?? "—"}</strong>
          <small>Explicit access grants</small>
        </div>
        <div>
          <span>Approved policy</span>
          <strong className="metric-word">Pending</strong>
          <small>Authority approval required</small>
        </div>
      </div>
      {clients.error && <ErrorNotice message={clients.error} retry={refresh} />}
      <div className="overview-grid">
        <section className="primary-region">
          <div className="section-heading">
            <div>
              <h2>Organization register</h2>
              <p>Records available to this workspace</p>
            </div>
            <button
              className="text-button"
              onClick={() => navigate("organizations")}
            >
              View register ↗
            </button>
          </div>
          {organizations.loading ? (
            <Loading />
          ) : organizations.error ? (
            <ErrorNotice message={organizations.error} retry={refresh} />
          ) : (
            <OrganizationTable records={organizations.data?.results || []} />
          )}
        </section>
        <aside className="cycle-context" aria-label="Reference cycle">
          <p className="eyebrow">CYCLE CONTEXT</p>
          {cyclesLoading ? (
            <Loading />
          ) : cyclesError ? (
            <ErrorNotice message={cyclesError} retry={refresh} />
          ) : cycle ? (
            <>
              <span className="badge candidate">Candidate calendar</span>
              <h2>
                {dateOnly(cycle.broadcast_start).split(" ").slice(1).join(" ")}
              </h2>
              <p className="muted">Broadcast period</p>
              <div className="context-detail">
                <span>Period</span>
                <strong>
                  {dateOnly(cycle.broadcast_start)} –{" "}
                  {dateOnly(cycle.broadcast_end)}
                </strong>
              </div>
              <div className="context-detail">
                <span>Policy reference</span>
                <strong>
                  {cycle.policy.code} · v{cycle.policy.version}
                </strong>
              </div>
              <div className="context-detail">
                <span>Approval</span>
                <strong>Not approved</strong>
              </div>
              <button
                className="text-button"
                onClick={() => navigate("calendar")}
              >
                Inspect calendar ↗
              </button>
            </>
          ) : (
            <Empty title="Calendar not configured">
              No candidate cycle is visible in this workspace.
            </Empty>
          )}
        </aside>
      </div>
      <section className="next-step">
        <span className="step-number">NEXT</span>
        <div>
          <h2>
            {membership.can_prepare_policy
              ? "Prepare the source register"
              : membership.can_stage_complaints
                ? "Prepare a complaint import"
                : membership.can_view_claims
                  ? "Review filed reports"
                  : "Review the foundation records"}
          </h2>
          <p>
            {membership.can_prepare_policy
              ? "Save candidate versions with the exact source reference and digest. Independent approval comes in a later delivery."
              : membership.can_stage_complaints
                ? "Stage a fictional CSV, review row feedback and pass the ready rows to a channel approver."
                : membership.can_view_claims
                  ? "Reported claims are available within your scope. Payment, disputes and verified settlement remain separate."
                  : "Check organization identities and permitted client visibility."}
          </p>
        </div>
      </section>
    </>
  );
}

function OrganizationTable({ records }: { records: Organization[] }) {
  if (!records.length)
    return (
      <Empty title="No organization records">
        No records match this workspace or search.
      </Empty>
    );
  return (
    <div
      className="table-scroll"
      role="region"
      aria-label="Organization records"
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th>Organization</th>
            <th>Type</th>
            <th>Record</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id}>
              <td>
                <div className="record-name">
                  <span
                    className={`org-initial ${record.kind}`}
                    aria-hidden="true"
                  >
                    {record.legal_name.replace("Sample ", "").slice(0, 1)}
                  </span>
                  <div>
                    <strong>{record.legal_name}</strong>
                    <small>{record.code}</small>
                  </div>
                </div>
              </td>
              <td>
                <span className="kind-label">
                  {record.kind === "pba" ? "Operations" : record.kind}
                </span>
              </td>
              <td>
                <span className={record.is_demo ? "badge neutral" : "badge"}>
                  {record.is_demo
                    ? "Fictional"
                    : record.is_active
                      ? "Active record"
                      : "Inactive record"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RegistryList({
  kind,
  membership,
  environment,
  revision,
  refresh,
}: {
  kind: "organizations" | "clients";
  membership: Membership;
  environment: string;
  revision: number;
  refresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const debounced = useDebounced(query);
  const result = useResource<Page<Organization | Client>>(
    `/registry/${kind}/?page=${page}&q=${encodeURIComponent(debounced)}`,
    membership.organization.id,
    revision,
  );
  return (
    <section>
      <div className="list-toolbar">
        <label className="search-field">
          <Icon path="M21 21l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14" />
          <span className="sr-only">Search {kind}</span>
          <input
            placeholder={`Search ${kind === "clients" ? "clients" : "organizations"} by name…`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </label>
        {membership.can_manage_registry && environment === "development" && (
          <button
            className="primary-button"
            onClick={() => {
              setNotice("");
              setAdding(true);
            }}
          >
            <span aria-hidden="true">＋</span>Add{" "}
            {kind === "clients" ? "client" : "organization"}
          </button>
        )}
      </div>
      {notice && (
        <p className="success-notice" role="status">
          {notice}
        </p>
      )}
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorNotice message={result.error} retry={refresh} />
      ) : (
        <>
          {kind === "organizations" ? (
            <OrganizationTable
              records={(result.data?.results || []) as Organization[]}
            />
          ) : result.data?.results.length ? (
            <div
              className="table-scroll"
              role="region"
              aria-label="Client records"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Legal client</th>
                    <th>Reference</th>
                    <th>Record</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.data.results as Client[]).map((client) => (
                    <tr key={client.id}>
                      <td>
                        <strong>{client.legal_name}</strong>
                      </td>
                      <td className="mono">{client.code}</td>
                      <td>
                        <span className="badge neutral">
                          {client.is_demo ? "Fictional" : "Registry entry"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No client records">
              No permitted client records match this search.
            </Empty>
          )}
          <Pager
            count={result.data?.count || 0}
            page={page}
            hasNext={!!result.data?.next}
            setPage={setPage}
          />
        </>
      )}
      {adding && (
        <RegistryForm
          kind={kind}
          organizationId={membership.organization.id}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            setPage(1);
            setQuery("");
            setNotice(
              "Registry entry saved. Its creation is recorded in the activity log.",
            );
            refresh();
          }}
        />
      )}
    </section>
  );
}

function Calendar({ cycle }: { cycle?: Cycle }) {
  if (!cycle)
    return (
      <Empty title="No candidate calendar">
        Calendar coverage and exact cutoff times must be supplied before
        clearance intake can be enabled.
      </Empty>
    );
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>{cycle.title}</h2>
          <p>
            {dateOnly(cycle.broadcast_start)} – {dateOnly(cycle.broadcast_end)}
          </p>
        </div>
        <span className="badge candidate">Not approved</span>
      </div>
      <div className="calendar-layout">
        <ol className="milestone-list">
          {cycle.milestones.map((milestone, index) => (
            <li key={milestone.id}>
              <span className="milestone-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h3>{milestone.label}</h3>
                <p>
                  {dateTime(milestone.occurs_at)} <span>PKT</span>
                </p>
              </div>
              <span className="badge neutral">Candidate</span>
            </li>
          ))}
        </ol>
        <aside className="source-panel" aria-label="Policy source">
          <p className="eyebrow">SOURCE & PROVENANCE</p>
          <h3>{cycle.policy.title}</h3>
          <dl>
            <dt>Policy version</dt>
            <dd>
              {cycle.policy.code} · v{cycle.policy.version}
            </dd>
            <dt>Source reference</dt>
            <dd>{cycle.policy.source_reference}</dd>
            <dt>Source SHA-256</dt>
            <dd className="digest">{cycle.policy.source_sha256}</dd>
          </dl>
          <p className="muted small-copy">
            The supplied digest identifies a source reference. This candidate
            has no approval or enforcement effect.
          </p>
        </aside>
      </div>
    </section>
  );
}

function PolicyList({
  membership,
  environment,
  revision,
  refresh,
}: {
  membership: Membership;
  environment: string;
  revision: number;
  refresh: () => void;
}) {
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const policies = useResource<Page<Policy>>(
    `/policies/?page=${page}`,
    membership.organization.id,
    revision,
  );
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Candidate policy versions</h2>
          <p>Prior versions are preserved when a new version is recorded.</p>
        </div>
        {membership.can_prepare_policy && environment === "development" && (
          <button
            className="primary-button"
            onClick={() => {
              setNotice("");
              setAdding(true);
            }}
          >
            ＋ New candidate
          </button>
        )}
      </div>
      {notice && (
        <p role="status" className="success-notice">
          {notice}
        </p>
      )}
      {policies.loading ? (
        <Loading />
      ) : policies.error ? (
        <ErrorNotice message={policies.error} retry={refresh} />
      ) : (
        <>
          {policies.data?.results.length ? (
            <div className="policy-list">
              {policies.data.results.map((policy) => (
                <article className="policy-entry" key={policy.id}>
                  <div className="policy-entry-head">
                    <div>
                      <span className="eyebrow">
                        {policy.code} / VERSION {policy.version}
                      </span>
                      <h3>{policy.title}</h3>
                    </div>
                    <span className="badge candidate">
                      Candidate · not approved
                    </span>
                  </div>
                  <dl>
                    <div>
                      <dt>Proposed interval</dt>
                      <dd>
                        {dateOnly(policy.effective_from)}
                        {policy.effective_until
                          ? ` – ${dateOnly(policy.effective_until)} (exclusive)`
                          : " onward"}
                      </dd>
                    </div>
                    <div>
                      <dt>Source reference</dt>
                      <dd>{policy.source_reference}</dd>
                    </div>
                    <div className="wide-field">
                      <dt>Source SHA-256 supplied by author</dt>
                      <dd className="digest">{policy.source_sha256}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          ) : (
            <Empty title="No policy candidates">
              A policy preparer must supply a source-linked candidate before
              calendar configuration.
            </Empty>
          )}
          <Pager
            count={policies.data?.count || 0}
            page={page}
            hasNext={!!policies.data?.next}
            setPage={setPage}
          />
        </>
      )}
      {adding && (
        <PolicyForm
          organizationId={membership.organization.id}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            setPage(1);
            setNotice(
              "Candidate saved. It remains unapproved and has no enforcement effect.",
            );
            refresh();
          }}
        />
      )}
    </section>
  );
}

function Activity({
  membership,
  revision,
  refresh,
}: {
  membership: Membership;
  revision: number;
  refresh: () => void;
}) {
  const [page, setPage] = useState(1);
  const activity = useResource<Page<AuditEvent>>(
    `/audit/?page=${page}`,
    membership.organization.id,
    revision,
  );
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Workspace history</h2>
          <p>
            Application actions are append-only. Retention exports remain a
            release gate.
          </p>
        </div>
        <button className="small-button" onClick={refresh}>
          Refresh
        </button>
      </div>
      {activity.loading ? (
        <Loading />
      ) : activity.error ? (
        <ErrorNotice message={activity.error} retry={refresh} />
      ) : (
        <>
          {activity.data?.results.length ? (
            <div
              className="table-scroll"
              role="region"
              aria-label="Activity history"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Time · PKT</th>
                    <th>Request reference</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.data.results.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <strong>
                          {event.action
                            .replaceAll(".", " / ")
                            .replaceAll("_", " ")}
                        </strong>
                        <small className="subject-reference">
                          {event.subject_id.slice(0, 8)}
                        </small>
                      </td>
                      <td>{event.actor_name}</td>
                      <td className="nowrap">{dateTime(event.occurred_at)}</td>
                      <td className="mono">
                        {event.request_id?.slice(0, 8) || "Local provisioning"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No workspace activity">
              Recorded actions for this organization will appear here.
            </Empty>
          )}
          <Pager
            count={activity.data?.count || 0}
            page={page}
            hasNext={!!activity.data?.next}
            setPage={setPage}
          />
        </>
      )}
    </section>
  );
}

function RegistryForm({
  kind,
  organizationId,
  onClose,
  onSaved,
}: {
  kind: "organizations" | "clients";
  organizationId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const options = useResource<Page<Organization>>(
    "/registry/organizations/?page_size=100",
    organizationId,
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const body =
      kind === "organizations"
        ? {
            legal_name: data.get("legal_name"),
            code: data.get("code"),
            kind: data.get("kind"),
          }
        : {
            legal_name: data.get("legal_name"),
            code: data.get("code"),
            participant_ids: data.getAll("participant_ids"),
          };
    setBusy(true);
    setError(null);
    try {
      await api(`/registry/${kind}/`, { organizationId, body });
      onSaved();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={`Add ${kind === "clients" ? "client" : "organization"}`}
      busy={busy}
      onClose={onClose}
    >
      <form className="stack-form" onSubmit={submit}>
        <label>
          Legal name
          <input name="legal_name" required maxLength={200} autoFocus />
        </label>
        <label>
          Unique reference
          <input
            name="code"
            required
            pattern={REFERENCE_PATTERN}
            maxLength={40}
            placeholder="e.g. sample-agency"
          />
          <span className="field-hint">
            Letters, numbers, hyphens and underscores.
          </span>
        </label>
        {kind === "organizations" ? (
          <label>
            Organization type
            <select name="kind">
              <option value="agency">Agency</option>
              <option value="channel">Channel</option>
            </select>
          </label>
        ) : (
          <label>
            Participating workspaces
            <select
              name="participant_ids"
              multiple
              required
              size={5}
              disabled={!options.data}
            >
              {options.data?.results
                .filter((o) => o.kind !== "pba" && o.is_active)
                .map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.legal_name}
                  </option>
                ))}
            </select>
            <span className="field-hint">
              Visibility only. This does not create an agency appointment.
            </span>
            {options.error && (
              <span role="alert" className="form-error">
                {options.error}
              </span>
            )}
          </label>
        )}
        <FormError error={error} />
        <div className="dialog-actions">
          <button
            type="button"
            className="small-button"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            className="primary-button"
            disabled={busy || (kind === "clients" && !options.data)}
          >
            {busy ? "Saving…" : "Save registry entry"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function PolicyForm({
  organizationId,
  onClose,
  onSaved,
}: {
  organizationId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const body = {
      ...Object.fromEntries(data),
      version: Number(data.get("version")),
      effective_until: data.get("effective_until") || null,
    };
    setBusy(true);
    setError(null);
    try {
      await api("/policies/", { organizationId, body });
      onSaved();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Record a candidate policy" busy={busy} onClose={onClose}>
      <p className="muted dialog-description">
        Candidates preserve the supplied source metadata. They require a
        separate authority approval process before use.
      </p>
      <form onSubmit={submit} className="stack-form">
        <label>
          Title
          <input name="title" required maxLength={200} autoFocus />
        </label>
        <div className="form-columns">
          <label>
            Policy reference
            <input
              name="code"
              required
              pattern={REFERENCE_PATTERN}
              maxLength={40}
            />
          </label>
          <label>
            Version
            <input
              name="version"
              type="number"
              min="1"
              step="1"
              required
              defaultValue="1"
            />
          </label>
        </div>
        <label>
          Source reference
          <input name="source_reference" required maxLength={255} />
        </label>
        <label>
          Source SHA-256
          <input
            name="source_sha256"
            required
            pattern="[a-f0-9]{64}"
            minLength={64}
            maxLength={64}
            className="mono"
          />
          <span className="field-hint">
            64 lowercase hexadecimal characters from the exact source bytes.
          </span>
        </label>
        <div className="form-columns">
          <label>
            Effective from
            <input name="effective_from" type="date" required />
          </label>
          <label>
            Effective until (exclusive)
            <input name="effective_until" type="date" />
          </label>
        </div>
        <FormError error={error} />
        <div className="dialog-actions">
          <button
            type="button"
            className="small-button"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
          <button className="primary-button" disabled={busy}>
            {busy ? "Saving…" : "Save candidate"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
