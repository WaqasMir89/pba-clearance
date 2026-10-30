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
