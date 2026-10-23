# Attack Surface Management (ASM)

Multi-tenant external attack-surface management: authorized discovery, asset and
service inventory, certificate monitoring, configuration-change history,
vulnerability and finding workflows, explainable risk scoring, alerts and CSV
reporting.

The product is deliberately conservative about what it claims. Seed rows are
labelled **Sample data**, live observations are labelled **Observed live**, and
features that are not built (cloud connectors, PDF export, outbound channels)
are rejected or marked unavailable instead of being simulated.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Request lifecycle, tenancy enforcement, data model, discovery pipeline, risk model, frontend structure, and where the unimplemented pieces would slot in. |
| [Contributing](CONTRIBUTING.md) | Local setup, the checks CI runs, backend/frontend conventions, and the honesty rule for unimplemented capabilities. |
| [Security policy](SECURITY.md) | Disclosure channel, intended-use constraints enforced by the code, and hardening steps before a real deployment. |

Continuous integration (`.github/workflows/ci.yml`) runs the pytest suite on
Python 3.12 and 3.13, applies migrations to a fresh database, typechecks and
builds the frontend, and validates the Compose configuration.

## Feature status

| Area | Status | Notes |
| --- | --- | --- |
| Companies, users, RBAC, tenant isolation | Implemented | Super Admin, Company Admin, Security Analyst, Read-Only Auditor. Non-members receive `404`, not `403`. |
| Asset inventory | Implemented | Domains, subdomains, IPs, services, API endpoints, web apps, cloud-resource records. Manual registration, CSV import (dry-run supported), CSV export, retirement. |
| Discovery | Implemented | Passive DNS (`dnspython`), certificate transparency (`crt.sh`), TLS handshake, HTTP fingerprinting, TCP connect port checks. |
| Automatic asset retirement | **Not implemented** | Retirement is manual; DNS/IP record removals are tracked as change events. There is no absence-based auto-retirement window. |
| Scan authorization gate | Implemented | Approved + unexpired ownership record required per target; active probes also require `allow_active_probing`; fail-closed matching. Four-eyes approval. |
| Cloud inventory | **Not implemented** | `cloud_inventory` capability is reported as unimplemented and scan requests are rejected. Cloud rows in demo data are sample rows. |
| Exposed services | Implemented | Observed by authorized port checks; risk classification for database, management and remote-access exposure. |
| Configuration-change history | Implemented | DNS, IP, service and certificate changes detected between observations; review state. |
| Certificate monitoring | Implemented | Expiry, hostname mismatch, self-signed, weak signature; expiry thresholds configurable. The scanning worker must run to refresh observations. |
| Vulnerabilities & findings | Implemented | CVE/CVSS records, findings, remediation tasks, assignment and status workflow. |
| Risk scoring | Implemented | Explainable model `2026.10`; per-finding factors, asset and company aggregation, classification and driver summary. |
| Alerts & notifications | Implemented (in-app) | Inbox, acknowledge/dismiss/resolve, notification centre, per-user minimum severity / muted types / in-app channel. |
| Email, webhook, Slack, digest | **Not implemented** | No outbound transport or digest scheduler exists. Preferences for these are not offered as working channels. |
| Reports | Implemented (CSV) | Asset, finding, vulnerability and certificate exports. Every export is recorded in the catalogue; files are streamed and not retained server-side. |
| PDF export | **Not implemented** | The API rejects PDF and the UI disables the action. |
| Cloud provider connectors | **Not implemented** | AWS/Azure/GCP integration status is reported honestly as unavailable. |
| Scheduled scans / retention purge | **Not implemented** | Scan history is real, but there is no scheduler; retention values are exposed as settings only. |

## Quick start (local, SQLite)

Prerequisites: Python 3.12+ (3.13 tested), Node.js 20+ (22 tested).

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --reset --companies 3
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5180>. The Vite dev server proxies `/api` to
`http://127.0.0.1:8010`. API documentation is at
<http://127.0.0.1:8010/docs>.

Development defaults live in `backend/app/core/config.py`; copy
`backend/.env.example` to `backend/.env` to override them. The default SQLite
file is `backend/asm.db`.

### Demo accounts

Seeded password for all accounts: `AsmDemo!2026`

| Account | Role | Access |
| --- | --- | --- |
| `platform@asm.example` | Super Admin | All companies, platform users, audit, settings |
| `admin@northwind.example` | Company Admin | Northwind Technologies |
| `analyst@northwind.example` | Security Analyst | Northwind; read-only auditor in Meridian |
| `auditor@meridian.example` | Read-Only Auditor | Meridian Health Group |
| `analyst@atlas.example` | Security Analyst | Atlas Financial |
| `former@northwind.example` | Read-Only Auditor | Disabled account (sign-in rejected) |

This block is hidden in production builds unless the host is `localhost` or
`127.0.0.1`.

## Authorization model

Discovery is fail-closed by design:

1. A `Company` record alone never authorizes a scan.
2. An `AuthorizationRecord` must be `approved`, unexpired and match every target.
   Supported scopes: `domain`, `wildcard_domain`, `url`, `ipv4`, `ipv6`, `cidr`.
3. Active probe types (TLS, HTTP, port checks, full recon) additionally require
   `allow_active_probing` on the record and must not be blocked by global
   offline mode or tenant safe mode.
4. The request must include `confirm_authorized`, which is stored in the audit
   record — consent is attributable, not implied.
5. The worker re-checks scope immediately before probing.

The requester of an authorization record cannot approve it, except a Super Admin
(four-eyes rule). Seeded Northwind/Atlas records are demonstration records and
their evidence text says so.

## Docker Compose (PostgreSQL + Redis + Celery)

```bash
cp .env.example .env
# Edit .env: set ASM_SECRET_KEY and POSTGRES_PASSWORD (both are required)
docker compose up --build
```

The stack listens on <http://localhost:8080> (override with `ASM_WEB_PORT`).
Nginx serves the built SPA, proxies `/api` to the API container, and the Celery
worker runs scans. The API container runs `alembic upgrade head` before serving.

Optional local-demo data (never against a production database):

```bash
docker compose --profile demo run --rm seed
```

Compose intentionally does not seed automatically. For TLS, terminate HTTPS at
an external reverse proxy or load balancer in front of the published web port;
the provided nginx config is HTTP-only.

## Tests

```bash
cd backend
pytest -q
```

Coverage includes health checks, authentication, RBAC, cross-tenant `404`s,
four-eyes approval, CSV import/idempotency, scan scope enforcement and
unimplemented-type rejection, alert-preference fan-out, risk scoring and
certificate status thresholds. Tests use a throwaway SQLite database and never
touch the dev database or the network (active probes are disabled).

```bash
cd frontend
npm run typecheck   # tsc -b, strict + noUnusedLocals
npm run build       # typecheck + production build
```

## Architecture

```
backend/
  app/
    api/v1/          REST endpoints (auth, companies, assets, scans, findings,
                     vulnerabilities, certificates, changes, alerts, reports,
                     users, settings, meta, integrations)
    core/            settings, security, RBAC matrix, error envelopes, logging
    db/              async engine/session, portable types
    discovery/       DNS/CT/TLS/HTTP/port checks, authorization gate, engine
    jobs/            in-process runner and Celery task
    models/          SQLAlchemy 2.0 models (27 tables)
    services/        risk model, presenters, finding/alert workflows, dashboard
    seed.py          deterministic, clearly labelled demo data
  alembic/           async migrations (SQLite batch mode + PostgreSQL)
  tests/             pytest integration suite
frontend/
  src/
    features/        login, dashboard, companies, assets, domains, IPs, APIs,
                     cloud, certificates, vulnerabilities, findings, changes,
                     alerts, reports, scans, users, settings, 404
    components/      layout, UI primitives, shared table/stat components
    context/         AuthProvider (session, permissions, company selection)
    lib/             typed API client, API types, labels, charts, utilities
```

### Data model highlights

- Every tenant-owned row carries `company_id`; tenant routes resolve it through
  a single dependency that checks capability **and** membership.
- `RecordSource` + `Provenance` preserve where each row came from (`seed`,
  passive DNS, CT, TLS, HTTP, CSV import, manual, cloud connector, etc.).
- `Scan.produced_live_data` records whether a run reached the network; reporting
  never presents a simulated run as live output.
- Risk scores store their factors (`score_factors`) so a rating can be audited.

## Security notes and limitations

- Passwords use PBKDF2-HMAC-SHA256 (600,000 iterations by default); JWT access
  and refresh tokens are signed with `ASM_SECRET_KEY`. Replace the development
  secret and serve over HTTPS in production.
- Login lockout is enforced after repeated failures. Failed-password bodies are
  not echoed into responses or logs; the audit trail records security events.
- The in-process rate limiter is per worker. Use a gateway/WAF limit as well.
- There is no email transport, webhook delivery, Slack integration, digest
  scheduler, cloud connector, PDF renderer or retention purge job. Those
  capabilities are not pretended to work.
- Discovery is limited by policy (targets/run, concurrency, rate, ports, timeout,
  offline switch) and only runs against approved scopes.
- The demo seed uses deterministic randomized fixtures, not live scan results.
  Every fixture row is tagged as sample data.

## Environment variables

See `backend/.env.example` and the root `.env.example` for the Compose stack.
Notable settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ASM_APP_ENV` | `development` | `development`, `test`, `staging`, `production` |
| `ASM_DATABASE_URL` | SQLite file | `postgresql+asyncpg://…` in production |
| `ASM_SECRET_KEY` | dev-only value | Token signing; required in production |
| `ASM_JOB_BACKEND` | `in-process` | `celery` uses `ASM_REDIS_URL` |
| `ASM_DISCOVERY_ENABLED` | `true` | Global discovery switch |
| `ASM_DISCOVERY_OFFLINE` | `false` | Block all outbound probing |
| `ASM_DEMO_MODE` | `true` | Marks/labels demo behaviour |
| `ASM_CERTIFICATE_EXPIRY_WARNING_DAYS` | `30` | Expiring-soon threshold |
| `ASM_CERTIFICATE_EXPIRY_CRITICAL_DAYS` | `7` | Elevates expiring severity |
| `ASM_SCAN_MAX_TARGETS_PER_RUN` | `250` | Per-run target cap |
| `ASM_RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | Per-IP, per-worker limit |
