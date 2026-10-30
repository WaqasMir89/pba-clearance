export type Organization = {
  id: string;
  code: string;
  legal_name: string;
  kind: "pba" | "channel" | "agency";
  is_active: boolean;
  is_demo: boolean;
  created_at: string;
};
export type Client = {
  id: string;
  code: string;
  legal_name: string;
  is_demo: boolean;
  created_at: string;
};
export type Membership = {
  id: string;
  organization: Organization;
  role: string;
  role_label: string;
  can_manage_registry: boolean;
  can_view_audit: boolean;
  can_view_policy: boolean;
  can_prepare_policy: boolean;
  can_stage_complaints: boolean;
  can_file_complaints: boolean;
  can_view_claims: boolean;
  can_stage_objections: boolean;
  can_sign_objections: boolean;
  can_add_evidence: boolean;
};
export type Session = {
  user: { id: string; username: string; name: string };
  memberships: Membership[];
  environment: string;
  enforcement_enabled: boolean;
};
export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
export type Policy = {
  id: string;
  code: string;
  version: number;
  title: string;
  source_reference: string;
  source_sha256: string;
  effective_from: string;
  effective_until: string | null;
  is_demo: boolean;
  status: "candidate";
  created_at: string;
};
export type Milestone = {
  id: string;
  code: string;
  label: string;
  local_date: string;
  local_time: string;
  timezone_name: string;
  occurs_at: string;
};
export type Cycle = {
  id: string;
  code: string;
  title: string;
  policy: Policy;
  broadcast_start: string;
  broadcast_end: string;
  milestones: Milestone[];
};
export type AuditEvent = {
  id: string;
  action: string;
  subject_type: string;
  subject_id: string;
  actor_name: string;
  request_id: string | null;
  occurred_at: string;
};

export type IntakeOptions = {
  agencies: { id: string; code: string; legal_name: string }[];
  clients: {
    id: string;
    code: string;
    legal_name: string;
    agency_ids: string[];
  }[];
  client_count: number;
  client_limit: number;
  max_source_bytes: number;
  max_rows: number;
  required_headers: string[];
  optional_headers: string[];
  declaration: { version: string; text: string };
};
export type RowStatus = "ready" | "invalid" | "review" | "duplicate";
export type ImportRow = {
  id: string;
  number: number;
  values: Record<string, string>;
  canonical: Record<string, string | null> | null;
  status: RowStatus;
  issues: { field: string; code: string; message: string }[];
  duplicate_of_row: number | null;
  existing_invoice_id: string | null;
};
export type ImportListEntry = {
  id: string;
  channel_id: string;
  cycle_id: string;
  cycle_code: string;
  source_filename: string;
  source_sha256: string;
  created_at: string;
  created_by: string;
  row_count: number;
  is_demo: boolean;
  submission_id: string | null;
};
export type ImportDetail = ImportListEntry & {
  validator_version: string;
  preview_current: boolean;
  preview: {
    rows: ImportRow[];
    counts: Record<RowStatus, number>;
    ready_reported_total: string;
    preview_hash: string;
    checked_at: string;
  };
};
export type FilingPayload = {
  expected_preview_hash: string;
  simulation_at: string;
  declaration_version: string;
  declaration_accepted: true;
  idempotency_key: string;
};
export type Submission = {
  id: string;
  source_import_id: string;
  channel_id: string;
  submitted_by: string;
  submitted_at: string;
  simulation_at: string;
  content_hash: string;
  row_count: number;
  reported_total: string;
  receipt: {
    schema: string;
    is_demo: boolean;
    channel: { legal_name: string; code: string };
    source: { filename: string; sha256: string; import_id: string };
    cycle: { code: string; filing_opens_at: string; filing_closes_at: string };
    policy: { code: string; version: number; source_sha256: string };
    declaration: { version: string; text: string };
    rows: Record<string, string | number | null>[];
    excluded_rows: { number: number; status: RowStatus }[];
  };
};
export type Claim = {
  id: string;
  invoice_id: string;
  invoice_number: string;
  invoice_date: string;
  financial_year: string;
  channel_id: string;
  channel_name: string;
  agency_id: string;
  agency_name: string;
  client_id: string;
  client_name: string;
  principal_amount: string;
  gst_amount: string;
  invoice_total: string;
  reported_due: string;
  balance_explanation: string;
  currency: string;
  cycle_id: string;
  cycle_code: string;
  submission_id: string;
  submitted_at: string;
  objection_case_id: string | null;
  objection_revision_id: string | null;
  objection_version: number;
  objection_state: "none" | "open" | "withdrawn";
  disputed_amount: string;
};
export type ClaimSummary = {
  count: number;
  reported_due_total: string;
  currency: string;
  basis: "reported_only";
  is_demo: boolean;
  disputed_amount_total: string;
  active_objection_count: number;
  accepted_credit_total: string | null;
  verified_settlement_total: string | null;
  remaining_reportable_balance: string | null;
};
