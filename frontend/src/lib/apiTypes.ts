export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type SeverityCounts = {
  critical: number;
  high: number;
  medium: number;
  low: number;
  informational: number;
};

export type Provenance = {
  source: string;
  label: string;
  is_simulated: boolean;
  is_observed: boolean;
};

export type Membership = {
  company_id: string;
  company_name: string | null;
  company_slug: string | null;
  role_code: string;
  role_name: string | null;
  is_active: boolean;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  job_title: string | null;
  role_code: string;
  role_name: string | null;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  avatar_color: string | null;
  timezone: string;
  memberships: Membership[];
  created_at: string;
};

export type UserSummary = {
  id: string;
  email: string;
  full_name: string;
  role_code: string;
  is_active: boolean;
  avatar_color: string | null;
};

export type CompanyAccess = {
  company_id: string;
  name: string;
  slug: string;
  role_code: string;
  asset_count: number;
  risk_score: number;
  status: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  permissions: string[];
  companies: CompanyAccess[];
};

export type MeResponse = {
  user: User;
  permissions: string[];
  companies: CompanyAccess[];
  alert_counts: Record<string, number>;
};

export type RoleDefinition = {
  code: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
  tenant_scoped: boolean;
};

export type EnumOption = { value: string; label: string };

export type EnumMeta = {
  asset_types: EnumOption[];
  asset_statuses: EnumOption[];
  criticalities: EnumOption[];
  exposures: EnumOption[];
  severities: EnumOption[];
  finding_types: EnumOption[];
  finding_statuses: EnumOption[];
  vulnerability_statuses: EnumOption[];
  certificate_statuses: EnumOption[];
  change_types: EnumOption[];
  scan_types: EnumOption[];
  scan_statuses: EnumOption[];
  alert_types: EnumOption[];
  alert_statuses: EnumOption[];
  sources: EnumOption[];
  remediation_statuses: EnumOption[];
};

export type CompanySummary = {
  id: string;
  name: string;
  slug: string;
  industry: string;
  status: string;
  website: string | null;
  asset_count: number;
  risk_score: number;
  is_demo_tenant: boolean;
};

export type CompanyDetail = CompanySummary & {
  description: string | null;
  contact_email: string | null;
  contact_name: string | null;
  root_domains: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
  member_count: number;
  open_findings: number;
  severity_counts: SeverityCounts;
  authorized_scope_count: number;
  last_scan_at: string | null;
};

export type CompanyMember = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  job_title: string | null;
  role_code: string;
  role_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
  expires_at: string | null;
  avatar_color: string | null;
};

export type Authorization = {
  id: string;
  company_id: string;
  scope_type: string;
  value: string;
  status: string;
  method: string | null;
  evidence: string | null;
  notes: string | null;
  verified_at: string | null;
  verified_by_id: string | null;
  expires_at: string | null;
  allow_active_probing: boolean;
  max_ports_per_target: number;
  created_at: string;
  is_live: boolean;
};

export type ScanPolicy = {
  id: string;
  company_id: string;
  max_concurrency: number;
  requests_per_second: number;
  timeout_seconds: number;
  allowed_ports: number[];
  max_targets_per_run: number;
  respect_robots: boolean;
  safe_mode: boolean;
  business_hours_only: boolean;
};

export type DomainDetail = {
  fqdn: string;
  root_domain: string;
  host_label: string | null;
  is_subdomain: boolean;
  is_wildcard: boolean;
  registrar: string | null;
  nameservers: string[];
  dns_records: Array<Record<string, unknown>>;
  resolves_to: string[];
  web_server: string | null;
  http_status: number | null;
  http_title: string | null;
  technologies: string[];
  dns_resolved_at: string | null;
};

export type IPDetail = {
  address: string;
  version: string;
  is_private: boolean;
  reverse_dns: string | null;
  geo_country: string | null;
  geo_country_name: string | null;
  geo_city: string | null;
  asn: string | null;
  asn_organization: string | null;
  provider_hint: string | null;
  is_cloud_elastic_ip: boolean;
};

export type ApiDetail = {
  url: string;
  method: string;
  path: string | null;
  api_format: string | null;
  summary: string | null;
  auth_type: string | null;
  requires_auth: boolean;
  unauthenticated_access: boolean;
  is_deprecated: boolean;
  is_documented: boolean;
  version: string | null;
  last_status_code: number | null;
  last_latency_ms: number | null;
  response_media_type: string | null;
};

export type CloudDetail = {
  provider: string;
  account_id: string | null;
  account_alias: string | null;
  region: string | null;
  resource_type: string | null;
  external_id: string;
  public_access: boolean;
  public_acl: boolean;
  encrypted: boolean;
  logging_enabled: boolean;
  security_groups: unknown[];
  observed_at: string | null;
};

export type Service = {
  id: string;
  asset_id: string;
  host: string | null;
  port: number;
  transport: string;
  service_name: string | null;
  product: string | null;
  version: string | null;
  operating_system: string | null;
  state: string;
  protocol_category: string | null;
  is_encrypted: boolean;
  is_expected: boolean;
  is_risky: boolean;
  risk_level: string | null;
  recommendation: string | null;
  banner: string | null;
  first_seen: string | null;
  last_seen: string | null;
  source: string;
};

export type CertificateSummary = {
  id: string;
  host: string;
  port: number;
  subject_common_name: string | null;
  issuer_common_name: string | null;
  issuer_organization: string | null;
  not_after: string | null;
  days_remaining: number | null;
  status: string;
  is_expired: boolean;
  hostname_matches: boolean;
  observed_at: string | null;
  source: string;
};

export type Asset = {
  id: string;
  company_id: string;
  name: string;
  asset_type: string;
  status: string;
  criticality: string;
  exposure: string;
  description: string | null;
  owner: string | null;
  technical_contact: string | null;
  environment: string | null;
  url: string | null;
  tags: string[];
  source: string;
  first_seen: string | null;
  last_seen: string | null;
  last_changed_at: string | null;
  risk_score: number;
  risk_classification: string | null;
  open_findings: number;
  critical_findings: number;
  high_findings: number;
  created_at: string;
  updated_at: string;
  provenance: Provenance | null;
  domain: DomainDetail | null;
  ip: IPDetail | null;
  api: ApiDetail | null;
  cloud: CloudDetail | null;
  service_count: number;
};

export type AssetEvent = {
  id: string;
  asset_id: string;
  event_type: string;
  summary: string;
  detail: Record<string, unknown> | null;
  severity: string | null;
  source: string;
  occurred_at: string;
};

export type AssetDetail = Asset & {
  services: Service[];
  certificates: CertificateSummary[];
  findings_by_severity: Record<string, number>;
  events: AssetEvent[];
  change_count: number;
};

export type CsvImportResult = {
  total_rows: number;
  created: number;
  updated: number;
  skipped: number;
  errors: Array<{ row: number; message: string }>;
  dry_run: boolean;
};

export type DomainRow = {
  id: string;
  asset_id: string;
  fqdn: string;
  root_domain: string;
  host_label: string | null;
  is_subdomain: boolean;
  is_wildcard: boolean;
  resolves_to: string[];
  http_status: number | null;
  technologies: string[];
  source: string;
  asset_name: string | null;
  risk_score: number;
  criticality: string;
  last_seen: string | null;
};

export type IPRow = {
  id: string;
  asset_id: string;
  address: string;
  version: string;
  is_private: boolean;
  asn: string | null;
  asn_organization: string | null;
  geo_country_name: string | null;
  provider_hint: string | null;
  reverse_dns: string | null;
  asset_name: string | null;
  service_count: number;
  risk_score: number;
  last_seen: string | null;
};

export type ApiEndpointRow = {
  id: string;
  asset_id: string;
  url: string;
  method: string;
  api_format: string | null;
  auth_type: string | null;
  requires_auth: boolean;
  unauthenticated_access: boolean;
  is_deprecated: boolean;
  last_status_code: number | null;
  asset_name: string | null;
  risk_score: number;
};

export type CloudResourceRow = {
  id: string;
  asset_id: string;
  provider: string;
  account_alias: string | null;
  region: string | null;
  resource_type: string | null;
  external_id: string;
  public_access: boolean;
  encrypted: boolean;
  source: string;
  asset_name: string | null;
  risk_score: number;
};

export type ServiceSummary = {
  total: number;
  risky: number;
  unexpected: number;
  unencrypted: number;
  management_interfaces: number;
  by_category: Array<{ category: string; count: number }>;
};

export type CloudSummary = {
  total: number;
  public: number;
  unencrypted: number;
  no_logging: number;
  by_provider: Array<{ provider: string; count: number }>;
  by_type: Array<{ type: string; count: number }>;
};

export type Certificate = {
  id: string;
  company_id: string;
  asset_id: string | null;
  scan_id: string | null;
  host: string;
  port: number;
  server_name_indication: string | null;
  serial_number: string | null;
  fingerprint_sha256: string | null;
  subject_common_name: string | null;
  subject_organization: string | null;
  issuer_common_name: string | null;
  issuer_organization: string | null;
  issuer_country: string | null;
  subject_alternative_names: string[];
  san_wildcard: boolean;
  not_before: string | null;
  not_after: string | null;
  days_remaining: number | null;
  status: string;
  is_expired: boolean;
  is_self_signed: boolean;
  hostname_matches: boolean;
  is_wildcard: boolean;
  key_algorithm: string | null;
  key_size: number | null;
  signature_algorithm: string | null;
  tls_version: string | null;
  certificate_chain_length: number | null;
  ocsp_url: string | null;
  weak_key: boolean;
  deprecated_signature: boolean;
  error: string | null;
  source: string;
  observed_at: string | null;
  asset_name: string | null;
  expires_label: string | null;
};

export type CertificateHealth = {
  total: number;
  valid: number;
  expiring_soon: number;
  expired: number;
  hostname_mismatch: number;
  self_signed: number;
  weak_crypto: number;
  not_observed: number;
  closest_expiry_days: number | null;
  expiry_buckets: Array<{ label: string; key: string; count: number }>;
  issuers: Array<{ issuer: string; count: number }>;
};

export type Finding = {
  id: string;
  company_id: string;
  asset_id: string;
  asset_name: string | null;
  finding_type: string;
  title: string;
  description: string | null;
  evidence: string | null;
  severity: string;
  confidence: string;
  status: string;
  risk_score: number;
  score_factors: Record<string, unknown>;
  cvss_base_score: number | null;
  exposure: string | null;
  business_impact: string | null;
  recommendation: string | null;
  remediation_notes: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  evidence_count: number;
  source: string;
  provenance: Provenance | null;
  discovered_at: string;
  last_verified_at: string | null;
  remediated_at: string | null;
  due_date: string | null;
  sla_breached: boolean;
  task_count: number;
};

export type RemediationTask = {
  id: string;
  finding_id: string;
  asset_id: string | null;
  title: string;
  description: string | null;
  priority: string;
  status: string;
  assignee_id: string | null;
  assignee_name: string | null;
  due_date: string | null;
  completed_at: string | null;
  progress_percent: number;
  created_at: string;
};

export type FindingDetail = {
  finding: Finding;
  tasks: RemediationTask[];
};

export type Vulnerability = {
  id: string;
  company_id: string;
  asset_id: string;
  asset_name: string | null;
  cve_id: string;
  title: string;
  description: string | null;
  severity: string;
  cvss_base_score: number | null;
  cvss_vector: string | null;
  exploitability: string | null;
  in_ransomware_catalog: boolean;
  affected_product: string | null;
  affected_version: string | null;
  fixed_version: string | null;
  references: unknown[];
  confidence: string;
  status: string;
  remediation_note: string | null;
  recommendation: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  discovered_at: string | null;
  resolved_at: string | null;
  due_date: string | null;
  source: string;
  provenance: Provenance | null;
};

export type ConfigurationChange = {
  id: string;
  company_id: string;
  asset_id: string | null;
  asset_name: string | null;
  scan_id: string | null;
  change_type: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  summary: string;
  severity: string;
  is_suspicious: boolean;
  is_expected: boolean;
  is_unplanned_exposure: boolean;
  detail: Record<string, unknown>;
  source: string;
  occurred_at: string;
  acknowledged_at: string | null;
  acknowledged_by_id: string | null;
};

export type ChangeSummary = {
  total_30d: number;
  suspicious_30d: number;
  unplanned_exposure_30d: number;
  by_type: Array<{ type: string; count: number }>;
  by_severity: Array<{ severity: string; count: number }>;
};

export type Alert = {
  id: string;
  company_id: string;
  alert_type: string;
  severity: string;
  status: string;
  title: string;
  message: string;
  recommendation: string | null;
  asset_id: string | null;
  asset_name: string | null;
  finding_id: string | null;
  certificate_id: string | null;
  change_id: string | null;
  scan_id: string | null;
  payload: Record<string, unknown>;
  channels: string[];
  source: string;
  occurred_at: string;
  last_occurred_at: string | null;
  occurrence_count: number;
  acknowledged_at: string | null;
  acknowledged_by_id: string | null;
  acknowledged_by_name: string | null;
  dismissed_reason: string | null;
  resolved_at: string | null;
};

export type AlertCounts = {
  new: number;
  acknowledged: number;
  critical: number;
  high: number;
  unread_notifications: number;
};

export type Notification = {
  id: string;
  alert_id: string;
  company_id: string | null;
  title: string;
  message: string | null;
  severity: string;
  channel: string;
  read_at: string | null;
  created_at: string;
};

export type AlertPreference = {
  min_severity: string;
  channels: string[];
  muted_types: string[];
  daily_digest: boolean;
};

export type RiskFactor = {
  key: string;
  label: string;
  weight: number;
  contribution: number;
  description?: string | null;
};

export type RiskSummary = {
  score: number;
  classification: string;
  previous_score: number | null;
  delta: number | null;
  model_version: string;
  computed_at: string | null;
  factors: RiskFactor[];
  driver_summary: string | null;
  open_findings: number;
  severity_counts: SeverityCounts;
  note?: string;
};

export type TrendPoint = {
  date: string;
  assets: number;
  findings: number;
  risk_score: number;
  critical: number;
  high: number;
};

export type DashboardMetric = {
  total_assets: number;
  assets_new_7d: number;
  assets_changed_7d: number;
  assets_retired: number;
  domains: number;
  subdomains: number;
  ip_addresses: number;
  api_endpoints: number;
  cloud_resources: number;
  web_applications: number;
  services_total: number;
  certificates_total: number;
  findings_open: number;
  vulnerabilities_open: number;
  changes_7d: number;
  alerts_new: number;
  scans_7d: number;
  last_scan_at: string | null;
};

export type RecentEvent = {
  id: string;
  kind: string;
  title: string;
  detail: string | null;
  severity: string | null;
  asset_id: string | null;
  asset_name: string | null;
  occurred_at: string;
  source: string;
};

export type AssetTypeCount = {
  asset_type: string;
  label: string;
  count: number;
};

export type CompanyComparison = {
  company_id: string;
  name: string;
  slug: string;
  asset_count: number;
  open_findings: number;
  risk_score: number;
  critical_findings: number;
};

export type Dashboard = {
  company_id: string;
  company_name: string;
  generated_at: string;
  metrics: DashboardMetric;
  risk: RiskSummary;
  findings_by_severity: SeverityCounts;
  vulnerabilities_by_severity: SeverityCounts;
  asset_mix: AssetTypeCount[];
  service_snapshot: {
    total: number;
    risky: number;
    unexpected: number;
    unencrypted: number;
    management_interfaces: number;
    by_category: Array<{ category: string; count: number }>;
  };
  certificate_snapshot: {
    total: number;
    valid: number;
    expiring_soon: number;
    expired: number;
    hostname_mismatch: number;
    closest_expiry_days: number | null;
  };
  trend: TrendPoint[];
  recent_events: RecentEvent[];
  recent_changes: RecentEvent[];
  recent_alerts: RecentEvent[];
  top_risks: Finding[];
  companies: CompanyComparison[];
  data_provenance_note: string;
};

export type ScanCapability = {
  scan_type: string;
  label: string;
  description: string;
  implemented: boolean;
  required_authorization: boolean;
  intrusive: boolean;
  availability_note: string | null;
};

export type ScanEvent = {
  id: string;
  level: string;
  stage: string | null;
  message: string;
  detail: Record<string, unknown> | null;
  occurred_at: string;
};

export type Scan = {
  id: string;
  company_id: string;
  name: string | null;
  scan_type: string;
  status: string;
  trigger: string;
  requested_by_id: string | null;
  requested_by_email: string | null;
  authorization_record_id: string | null;
  targets: string[];
  targets_total: number;
  targets_completed: number;
  targets_failed: number;
  assets_discovered: number;
  assets_new: number;
  assets_changed: number;
  assets_removed: number;
  services_found: number;
  certificates_found: number;
  findings_created: number;
  changes_detected: number;
  progress_percent: number;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  result_summary: Record<string, unknown>;
  policy_snapshot: Record<string, unknown>;
  produced_live_data: boolean;
  created_at: string;
};

export type ScanDetail = Scan & { events: ScanEvent[] };

export type ReportRecord = {
  id: string;
  name: string;
  template: string;
  format: string;
  status: string;
  row_count: number;
  artifact_filename: string | null;
  generated_by_email: string | null;
  generated_at: string | null;
};

export type Integration = {
  id: string | null;
  name: string;
  kind: string;
  status: string;
  built_in: boolean;
  verified: boolean;
  enabled: boolean;
  capability: string | null;
  description: string | null;
  secret_keys: string[];
  last_run_at: string | null;
  last_error: string | null;
  implemented: boolean;
};

export type PlatformSettings = {
  app_name: string;
  app_env: string;
  api_prefix: string;
  discovery_enabled: boolean;
  discovery_offline: boolean;
  job_backend: string;
  demo_mode: boolean;
  certificate_expiry_warning_days: number;
  certificate_expiry_critical_days: number;
  rate_limit_enabled: boolean;
  rate_limit_requests_per_minute: number;
  retention: {
    scan_result_retention_days: number;
    audit_log_retention_days: number;
  };
  supported_integrations: string[];
};

export type AuditLogRow = {
  id: string;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  outcome: string;
  object_type: string | null;
  object_label: string | null;
  ip_address: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
};
