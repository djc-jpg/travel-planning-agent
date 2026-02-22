# Runtime Runbook

## 1. Modes and Expected Behavior

- `STRICT_EXTERNAL_DATA=true`
  - external required data unavailable -> request fails fast.
  - no silent provider downgrade.
- `STRICT_EXTERNAL_DATA=false`
  - degraded fallback allowed.
  - output must include runtime fingerprint for traceability.

## 2. Run Fingerprint Checklist

Each plan/chat response should expose:

- `run_mode` (`REALTIME` or `DEGRADED`)
- `poi_provider`
- `route_provider`
- `llm_provider`
- `strict_external_data`
- `env_source`
- `trace_id`

If these fields are missing, treat as trust defect.

## 3. Health and Diagnostics

- `GET /health`: liveness check
- `GET /metrics`: request/tool counters and latency
- `GET /diagnostics` (bearer token required):
  - tool backend state
  - cache stats
  - runtime flags
  - plan metrics snapshot

## 4. History and Export APIs

- `GET /sessions?limit=20`
  - returns recent session summaries.
- `GET /sessions/{session_id}/history?limit=20`
  - returns plan history list for one session.
- `GET /plans/{request_id}/export`
  - returns persisted request + plan + artifacts for export/reuse.
- `GET /plans/{request_id}/export?format=markdown`
  - returns Markdown export for direct copy/download.

## 5. Common Failure Patterns

1. `401/403` on API calls
- cause: `API_BEARER_TOKEN` enabled but token missing/wrong.
- action: send `Authorization: Bearer <token>`.

2. Strict mode request fails unexpectedly
- cause: provider key missing or upstream unavailable.
- action:
  - verify `AMAP_API_KEY` / LLM key.
  - run `python -m app.deploy.preflight`.
  - inspect `/diagnostics` tool backend status.

3. Output quality drops (non-experience POI, low realism)
- action:
  - run `python -m app.eval.run_eval`
  - run `python -m eval.release_gate_runner`
  - check `infrastructure_poi_rate`, `verified_fact_ratio`, `fallback_rate`.

4. Expected REALTIME but response is DEGRADED
- cause:
  - backend process loaded `.env` while keys are in `.env.prerelease`, or
  - `ROUTING_PROVIDER=fixture` explicitly overrides realtime routing.
- action:
  - verify active env file (`ENV_SOURCE`, compose `env_file`, startup command).
  - verify `ROUTING_PROVIDER` (`auto` or `real` for realtime).
  - check response `run_fingerprint`:
    - `poi_provider=amap`
    - `route_provider=real`
    - `llm_provider=dashscope/openai/llm_compatible`
    - `run_mode=REALTIME`

## 6. Release Validation Commands

```bash
python -m ruff check --select E9,F app tests tools eval
pytest -q -p no:cacheprovider
python -m app.eval.run_eval
python -m eval.release_gate_runner
python -m tools.release_summary
```

Gate should fail if hard thresholds are violated (example: L0 ratio, fallback rate, verified facts).

## 7. Incident Triage Order

1. Check `/health`.
2. Check `/metrics` and `/diagnostics`.
3. Confirm strict mode + provider keys.
4. Reproduce with one API call and capture `trace_id`.
5. Query export payload by `request_id` for full evidence.
