# Contributing

Thanks for taking a look. This repository is an external attack-surface
management tool, so the bar for changes is "does not pretend to do something it
does not do."

## Development setup

Prerequisites: Python 3.12 or newer (3.13 is what the suite is run on), Node.js
20 or newer.

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     POSIX: source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --reset --companies 3      # deterministic, labelled sample data
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

```bash
# Frontend, second terminal
cd frontend
npm ci
npm run dev            # http://localhost:5180, proxies /api to :8010
```

## Checks to run before a pull request

```bash
cd backend  && python -m pytest -q          # integration suite, no network
cd frontend && npm run typecheck && npm run build
```

Both are what CI runs, plus a fresh-database `alembic upgrade head` and
`docker compose config --quiet`.

The test suite builds its own throwaway SQLite file, forces
`ASM_DISCOVERY_OFFLINE=true`, and lowers the password iteration count. It never
touches `backend/asm.db`.

## Conventions

### Backend

- Everything is async. SQLAlchemy 2.0 typed mappings (`Mapped[str]`,
  `mapped_column`) and a single `AsyncSession` per request via `get_session`.
- Raise the typed errors from `app/core/errors.py`
  (`ValidationError_`, `NotFoundError`, `ScanAuthorizationError`, …). The handler
  turns them into the one envelope the frontend understands:
  `{ "error": { "code", "message", "details", "request_id" } }`. Do not hand-roll
  JSON error responses in routes.
- List endpoints take the shared `Pagination` dependency and return
  `Page.build(...)`; sorting goes through an explicit allow-list per resource.
- Permissions live in `app/core/permissions.py` only. Add the capability name to
  `PERMISSIONS`, then to the role lists that should hold it. Tenant routes resolve
  capability **and** membership through `tenant_dependency("<permission>")`;
  a caller who is not a member of the company gets `404`, never `403`.
- Any model change needs an Alembic revision that applies to both backends
  (SQLite revisions use batch mode). Verify with
  `ASM_DATABASE_URL=sqlite+aiosqlite:///./check.db alembic upgrade head`.
- New probes go in `app/discovery/checks.py`, are registered in `CAPABILITIES` in
  `app/api/v1/scans.py` with an accurate `implemented` flag, and must run behind
  `authorize_targets`. Nothing may bypass `ASM_DISCOVERY_OFFLINE`, the scan policy
  ceilings, or the per-target scope match.
- Never log secrets, token bodies or password material. Audit records carry the
  actor, action, target and request id.

### Frontend

- Pages live in `src/features/<area>`, shared primitives in `src/components/ui`
  and `src/components/common`, and all HTTP goes through the typed client in
  `src/lib/api.ts` with response types in `src/lib/apiTypes.ts`.
- Server state is TanStack Query; keep query keys aligned with the endpoint plus
  the selected company. Auth state and permission checks come from `useAuth()`.
- TypeScript is strict with `noUnusedLocals`/`noUnusedParameters`. `npm run
  typecheck` is the gate; the production build runs it too.
- Colour, spacing and severity tokens come from the CSS variables in `src/styles`.

### The honesty rule

This is the one convention that overrides convenience:

- A capability that does not exist is reported as not implemented and rejected by
  the API — cloud inventory scan types, PDF export, email/webhook/Slack delivery,
  scheduling, retention purge.
- Data that was seeded is tagged with its source (`RecordSource`/provenance) and
  labelled sample data in the UI. A simulated run never renders as a live scan,
  and `Scan.produced_live_data` records whether the network was reached.
- If you add a feature that only works partially, surface the part that works.

## Pull requests

- One coherent change per PR; describe the behaviour change and the "why".
- Include the commands you ran and their results.
- If you touched a model, an endpoint's authorization, or a discovery gate, say
  so explicitly in the description — those get the closest review.
- Update `README.md`'s feature-status table when a documented gap closes, and
  remove the matching "not implemented" row rather than leaving both.
