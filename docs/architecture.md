# Architecture

A walkthrough of how a request becomes a row, and how a row becomes a risk score.
The feature-status table in the root [README](../README.md) is authoritative on
what exists; this document describes how the existing parts fit together.

## Shape of the system

```
 browser ──> nginx (SPA + /api proxy)  ──> FastAPI app  ──> PostgreSQL / SQLite
                                                 │
                                                 ├──> in-process job runner
                                                 └──> Celery worker ──> Redis broker
                                                              │
                                                              └──> discovery engine ──> DNS / CT / TLS / HTTP / TCP
```

One process serves the API; scans run either on the API event loop
(`ASM_JOB_BACKEND=in-process`, no Redis needed) or in a Celery worker
(`ASM_JOB_BACKEND=celery`). Both paths call the same
`app.discovery.engine.run_scan(scan_id)` entry point, so a scan behaves the same
way whichever runner picked it up.

## Request lifecycle

`app/main.py` installs the cross-cutting layer once:

1. `RequestContextMiddleware` assigns or adopts `X-Request-ID`, applies a
   per-IP sliding-window rate limit, and emits one structured log line per
   request.
2. `CORSMiddleware` with an explicit origin list.
3. `install_error_handlers` maps `AppError` subclasses and unexpected exceptions
   to the single error envelope the frontend parses.
4. Routers under `settings.api_prefix` (`/api/v1`).
5. `get_session` yields a transactional `AsyncSession`: commit on success,
   rollback on any exception, so a route cannot half-persist a write.

Health endpoints (`/health`, `/health/ready`) sit outside the API prefix and are
exempt from rate limiting.

## Authentication and authorization

`app/core/security.py` handles PBKDF2-HMAC-SHA256 password hashing, access and
refresh token minting/verification (PyJWT, `ASM_SECRET_KEY`), and login lockout
after repeated failures.

`app/api/deps.py` is where tenancy is enforced:

- `get_current_user` resolves the bearer token to a `User`.
- `get_tenant_context` resolves the `company_id` in the path, checks the user is
  a member of that company, and materialises the effective permission set for
  that membership (`TenantContext`).
- `tenant_dependency("asset:read")` is the decorator every tenant-scoped route
  uses. Capability and membership are checked together, and a non-member receives
  `404` — the resource is not visible to them at all, so enumeration across
  tenants yields nothing.
- `require_platform_admin` guards the platform-only routes (`/users`, audit,
  global settings).
- `record_audit` writes actor, action, target and request id for security-
  relevant mutations.

Roles and their permission lists are declared once in `app/core/permissions.py`
and mirrored into the `roles` table by the migration/seed step, so the UI renders
available actions from the same source the API enforces.

## Data model

27 tables, grouped by concern (`app/models/`):

| Group | Tables | Notes |
| --- | --- | --- |
| Identity | `users`, `roles`, `company_memberships` | A user can hold a different role per company. |
| Tenant | `companies`, `authorization_records`, `scan_policies` | Ownership evidence and scanning ceilings. |
| Inventory | `assets`, `domains`, `ip_addresses`, `exposed_services`, `api_endpoints`, `cloud_resources`, `certificates`, `asset_events` | `assets` is the polymorphic head; type-specific rows hang off it by `asset_id`. |
| Change | `configuration_changes` | Diffs between successive observations. |
| Findings | `vulnerabilities`, `findings`, `remediation_tasks` | CVE/CVSS records, per-asset findings, task workflow. |
| Risk | `risk_scores` | Persisted score plus its `score_factors`. |
| Alerts | `alerts`, `notifications`, `alert_preferences` | Alert is the company-level event; notification is the per-user delivery. |
| Platform | `scans`, `scan_events`, `reports`, `integrations`, `audit_logs` | Operational history and provenance. |

Every tenant-owned row carries `company_id`. `RecordSource` plus provenance
columns record where a row came from (`manual`, `csv_import`, `seed`,
`passive_dns`, `passive_ct_log`, `active_tls_probe`, `active_http_probe`,
`active_port_probe`), which is what lets the UI distinguish sample data from
observed data — `OBSERVED_SOURCES` in `models/enums.py` is the set that counts as
a real observation.

## Discovery pipeline

`app/api/v1/scans.py` exposes `CAPABILITIES`, one entry per scan type with an
`implemented` flag and an `intrusive` flag. A request is rejected before any work
happens if the type is unimplemented, if `confirm_authorized` is missing, or if
the targets do not clear the authorization gate.

`app/discovery/gate.py` is the fail-closed matcher:

- `normalise_target` classifies a target as domain, wildcard domain, URL, IPv4,
  IPv6 or CIDR, and rejects ambiguous input.
- `target_in_scope` decides whether one authorization record covers one target;
  CIDR scopes carry a prefix floor so a record cannot smuggle in the internet.
- `record_is_live` requires `approved` status and a future `expires_at`.
- `authorize_targets` returns a per-target decision, and any target without a
  live covering record raises `ScanAuthorizationError` (`authorization_required`)
  before a `Scan` row is written.

`app/discovery/checks.py` holds the actual probes: `resolve_dns`,
`reverse_lookup`, `search_certificate_transparency` (crt.sh), `probe_tls`
(x509 via `cryptography`), `probe_http` (fingerprinting), and `check_ports`
(TCP connect only — no banner grabbing, no version probing, no payloads).

`app/discovery/engine.py` sequences them: expand targets under the policy
ceiling, authorise, resolve, diff against what is already stored, persist new or
changed rows with their source, then derive findings (`_certificate_findings`,
`_http_findings`, `_port_scan` classification) and alerts. Every stage appends a
`ScanEvent`, and `Scan.produced_live_data` records whether the network was
reached, so an offline or dry run is never presented as live output.

Concurrency, rate, per-probe timeout, max targets and the port list all come from
the tenant `ScanPolicy` clamped by global settings; `ASM_DISCOVERY_OFFLINE=true`
blocks active probes process-wide regardless of tenant policy.

## Risk model

`app/services/risk.py` implements model `2026.10`. `assess_finding` starts from
the severity implied by CVSS and multiplies by exploitability, exposure, asset
criticality and confidence factors, adds a bonus for confirmed public exploit,
and clamps to 0–10. `aggregate_asset_risk` and `aggregate_company_risk` roll that
up. The factor breakdown is stored with the score, so any rating on screen can be
explained and audited rather than being a magic number.

Classification thresholds live in `models/enums.py` (`classify`) and are shared by
the API and the frontend badges.

## Alerts

`app/services/findings.py` creates alerts for new assets, certificate expiry,
exposed services and risky changes, then fans them out to company users through
`notify_company_users`, which applies each user's `AlertPreference`: minimum
severity, muted alert types and channels. A company-specific preference overrides
the global one. Only `in_app` is a real channel today; the other kinds are not
offered as working options.

## Frontend

Vite + React 18 + TypeScript strict, TanStack Query for server state,
react-router for the 17 screens, Recharts for the dashboard.

- `src/context/AuthProvider.tsx` owns the session: token storage, single-flight
  refresh, the selected company, and `can(permission)` used by route guards and
  action buttons.
- `src/lib/api.ts` is the only place that talks HTTP. It unwraps the error
  envelope into `ApiError`, handles the refresh dance on `401`, and exposes
  `downloadPost`/`saveBlob` for CSV exports.
- `src/features/<area>` holds one page per screen; `src/components/ui` holds the
  primitives (table, badges, dialog, toast, empty/loading/error states).
- Routes are wrapped in `RequireAuth` plus a `RequirePermission` guard, so a
  Read-Only Auditor never sees a write affordance they would be rejected by.

## Where the missing pieces would go

These are deliberately absent, and each has an obvious seam:

- **Cloud inventory**: a connector per provider writing `cloud_resources` with
  its own `RecordSource`, plus flipping `cloud_inventory` to
  `implemented: true` in `CAPABILITIES`.
- **PDF reports**: a renderer behind the same `POST /companies/{id}/reports`
  contract; today the format check rejects `pdf` explicitly.
- **Outbound channels**: a transport interface next to
  `notify_company_users`, with preferences gating delivery per channel.
- **Scheduling**: a beat/cron source that enqueues `run_scan` for saved scopes;
  the scan contract already accepts everything a schedule needs.
- **Retention purge**: a job reading `scan_result_retention_days` and
  `audit_log_retention_days`, which are exposed as settings but not yet acted on.
