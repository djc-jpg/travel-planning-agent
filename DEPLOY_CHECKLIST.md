# trip-agent Deployment Checklist

Use this checklist to verify the project is release-ready before production rollout.

## 0. Bring Up Pre-release Stack (Docker)

Prepare env file:

```bash
cp .env.prerelease.example .env.prerelease
```

Windows one-click flow:

```powershell
.\scripts\prerelease.ps1
```

If Docker is unavailable, run local prerelease checks:

```powershell
.\scripts\prerelease-local.ps1
```

`prerelease-local` defaults to `ALLOW_INMEMORY_BACKEND=true` for single-node validation.
Use `.\scripts\prerelease-local.ps1 -StrictRedis` to require Redis connectivity.

Stop stack:

```powershell
.\scripts\prerelease-down.ps1
```

## 1. Environment Hard Checks

Run:

```bash
python -m app.deploy.preflight --env-file .env --skip-smoke
```

Expected:
- `FAIL=0`
- `WARN` only for intentionally accepted tradeoffs.

Recommended production defaults:
- `API_BEARER_TOKEN` set
- `ENABLE_DIAGNOSTICS=false` (or set `DIAGNOSTICS_TOKEN`)
- `STRICT_EXTERNAL_DATA=true` with valid `AMAP_API_KEY`
- scoped `CORS_ORIGINS` (no `*`)
- `REDIS_URL` set for multi-instance session consistency
- `ALLOW_INMEMORY_BACKEND=false` (set `true` only for single-node local runs)

## 2. Online Smoke Checks (Pre-release Environment)

Start backend, then run:

```bash
python -m app.deploy.preflight --env-file .env --base-url http://127.0.0.1:8000 --timeout 60
```

Expected:
- `/health` returns healthy
- `/plan` returns `200` or controlled `422`
- `/diagnostics` passes when diagnostics is enabled

## 3. Regression Gate

Backend:

```bash
ruff check --select E9,F app tests
pytest tests -q -p no:cacheprovider --timeout=30
python -m app.eval.run_eval
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

## 4. Release Decision

Block release when:
- any preflight `FAIL`
- backend/frontend regression command fails
- smoke checks return unexpected 5xx or auth errors
