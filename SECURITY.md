# Security policy

## Reporting a vulnerability

Please report security issues in this codebase privately rather than in a public
issue:

1. Use **Report a security vulnerability** on the repository's Security tab
   (GitHub private vulnerability reporting), or
2. Email the maintainer listed below.

```
security contact: <replace-with-your-security-email>
```

We aim to acknowledge within 5 business days and to ship a fix or a written
mitigation plan within 30. Please give us that window before disclosing
publicly.

## Intended use

This is an **external attack-surface management tool for assets you own or are
contractually authorized to assess.** It is not a scanning tool for arbitrary
third-party infrastructure.

The code enforces this rather than leaving it to the reader:

- Discovery and scanning require an `AuthorizationRecord` that is `approved`,
  unexpired and matches every target. Matching is fail-closed: no record, no scan.
- Active probe types (TLS handshake, HTTP fingerprinting, TCP port checks, full
  recon) additionally require `allow_active_probing` on that record.
- Every scan request must carry `confirm_authorized`, which is written into the
  audit trail with the requesting user and request id.
- The requester of an authorization record cannot approve it (four-eyes), except
  a platform Super Admin.
- Per-run ceilings are enforced in code: max targets, max concurrency, requests
  per second, per-probe timeouts, and a CIDR prefix floor.
- `ASM_DISCOVERY_OFFLINE=true` blocks all outbound probing process-wide, and
  tenant safe mode blocks ports regardless of the authorization record.

Do not weaken these gates in a fork that you run against infrastructure you do
not own.

## Hardening before you deploy this for anyone else

The defaults are development defaults on purpose. Before a real deployment:

- Set a strong `ASM_SECRET_KEY`. The process refuses to start in `production`
  with the shipped default value.
- Move `ASM_DATABASE_URL` to PostgreSQL and run `alembic upgrade head`; the
  automatic `create_all` path only applies to SQLite.
- Terminate HTTPS in front of the web container. The bundled nginx config is
  HTTP-only and exposes no certificate.
- Replace the seeded demo accounts. `app/seed.py` creates accounts with a known
  password and is never invoked by `docker-compose.yml` automatically — it sits
  behind an opt-in `demo` profile.
- Put a gateway-level rate limit in front of the API. The in-process limiter is
  per worker and is a safety valve, not a defence.
- Rotate anything you place in integration secret fields, and keep audit logs on
  storage the tenant users cannot read.

## Not covered

There is no threat-model claim, no pentest report and no certification attached
to this project. Outbound alert delivery (email, webhook, Slack), cloud
provider connectors, PDF rendering, scheduling and retention purge are **not
implemented**; the API rejects those requests instead of simulating them.
