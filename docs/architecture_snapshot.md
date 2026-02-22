# Architecture Snapshot (2026-02-21)

## 1. Runtime Call Graph

```text
CLI/API
  -> app.services.plan_service.execute_plan
    -> app.application.plan_trip.plan_trip
      -> intake -> retrieve -> planner -> trust/confidence -> output
        -> providers:
           - tool provider (poi/route/weather/calendar)
           - llm provider (qwen/openai/template)
      -> persistence (sqlite/noop)
      -> observability (metrics + structured logs)
```

## 2. Entry Points

- CLI: `python -m app.cli`
- API: `app/api/main.py` (`/plan`, `/chat`)
- Eval: `python -m app.eval.run_eval`
- Release gate: `python -m eval.release_gate_runner`

## 3. Provider Switch Points

- Tool provider switch: `app/adapters/tool_factory.py`
  - uses `AMAP_API_KEY`, `ROUTING_PROVIDER`, `STRICT_EXTERNAL_DATA`.
- LLM provider switch: `app/infrastructure/llm_factory.py`
  - priority: `DASHSCOPE_API_KEY > OPENAI_API_KEY > LLM_API_KEY > template`.
- Routing fallback transparency: `app/planner/routing_provider.py`
  - real failure must mark fallback source + lower routing confidence.

## 4. Strict Fail-Fast Path

- Preflight enforcement: `app/deploy/preflight.py`
- Runtime enforcement: `app/adapters/tool_factory.py`
- Behavior:
  - `STRICT_EXTERNAL_DATA=true` and required external data unavailable -> fail fast.
  - `STRICT_EXTERNAL_DATA=false` -> degraded path allowed, but run fingerprint records it.

## 5. Output Layer Separation

- User output shaping: `app/services/itinerary_presenter.py`
- Debug toggle:
  - default: hide debug fields in API output.
  - `debug=true`: include debug diagnostics fields.

## 6. Trust Layer Source of Truth

- Fact classification: `app/trust/facts/fact_classification.py`
- Confidence scoring: `app/trust/confidence.py`
- Integration point: `app/application/plan_trip.py`

## 7. Persistence and Product APIs

- Persistence backend: `app/persistence/sqlite_repository.py`
- Stored entities:
  - sessions
  - requests
  - plans
  - artifacts
- Read APIs:
  - `GET /sessions`
  - `GET /sessions/{session_id}/history`
  - `GET /plans/{request_id}/export`
  - `GET /plans/{request_id}/export?format=markdown`

## 8. Observability

- Health: `GET /health`
- Metrics snapshot: `GET /metrics`
- Diagnostics (token protected): `GET /diagnostics`
- Structured events:
  - tool latency/ok/error/returned_count
  - planner node start/end
  - retrieval semantic summary

## 9. Current Risk Points

- Multiple legacy namespaces coexist (`agent/*` and `application/*`), increasing cognitive load.
- Some repo files still use mixed encoding in docs/output examples.
- API layer still owns some response mapping details that can later move to dedicated presenters.

## 10. Dependency Direction (Target)

```text
api/cli
  -> services
    -> application
      -> domain
        -> providers(adapters)
      -> trust
      -> persistence
      -> observability
```

Rules:
- no service -> api reverse dependency
- no router business logic
- cross-layer payloads via explicit schemas, avoid free-form dict passing.
