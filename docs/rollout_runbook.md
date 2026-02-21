# Rollout Runbook (ENGINE_VERSION / STRICT_REQUIRED_FIELDS)

## 1. Scope

This runbook controls two runtime flags without code redeploy:

- `ENGINE_VERSION` (`v1` or `v2`)
- `STRICT_REQUIRED_FIELDS` (`true` or `false`)

Target behavior:

- `v1 + false`: legacy-compatible baseline
- `v2 + false`: new orchestration with soft required-field behavior
- `v2 + true`: strict required-field gate (missing required fields -> `clarifying`)

## 2. Preconditions

- `.env.prerelease` exists and contains valid auth tokens.
- `docker-compose.prerelease.yml` is available.
- Backend is reachable from the operator machine.

Recommended checks:

```powershell
.\scripts\prerelease.ps1
python tools/check_import_boundaries.py
python tools/check_single_entrypoint.py
```

## 3. Standard rollout path

Run automated canary + rollback drill:

```powershell
.\scripts\prerelease-rollout.ps1
```

This script executes four phases:

1. `baseline_v1` (`v1`, `false`)
2. `canary_v2_soft` (`v2`, `false`)
3. `canary_v2_strict` (`v2`, `true`)
4. `rollback_v1` (`v1`, `false`)

Each phase verifies:

- `/health`
- `app.deploy.preflight`
- `app.deploy.rollout_drill` behavior checks

## 4. Runtime observability

When diagnostics is enabled, inspect:

```http
GET /diagnostics
Authorization: Bearer <DIAGNOSTICS_TOKEN>
```

Fields to monitor:

- `runtime_flags.engine_version`
- `runtime_flags.strict_required_fields`
- `plan_metrics.status_counts`
- `plan_metrics.latency`

## 5. Emergency rollback

Immediate rollback to stable profile:

```powershell
.\scripts\prerelease-rollback.ps1
```

This enforces:

- `ENGINE_VERSION=v1`
- `STRICT_REQUIRED_FIELDS=false`

Then recreates backend container and runs preflight checks.

## 6. Exit criteria

Rollout is accepted when:

- all rollout phases pass
- no `FAIL` in preflight
- eval baseline remains stable
- frontend build/lint/typecheck pass

