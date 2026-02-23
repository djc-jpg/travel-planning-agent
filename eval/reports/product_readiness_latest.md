# Product Readiness Report

- generated_at: `2026-02-22T18:12:31Z`
- overall_passed: `True`

## Checks

| check | passed | detail | report |
| --- | --- | --- | --- |
| full_acceptance | True | full_passed=True | eval\reports\product_acceptance_latest.json |
| frontend_e2e | True | expected=3, unexpected=0 | eval\reports\frontend_e2e_latest.json |
| capacity_500_concurrency | True | success_rate=1.0000, p95_latency_ms=1722.40 | eval\reports\loadtest_20260222_174222.json |
| slo_degraded | True | success_rate=1.0000, p95_latency_ms=3680.47 | eval\reports\slo_latest.json |
| slo_realtime | True | success_rate=1.0000, p95_latency_ms=2567.70 | eval\reports\slo_realtime_latest.json |
| dependency_fault_drill | True | passed=True | eval\reports\dependency_fault_drill_latest.json |
| persistence_drill | True | passed=True | eval\reports\persistence_drill_latest.json |
| observability_stack | True | prometheus_ready=True, backend_target_healthy=True, grafana_ok=True, alert_rule_count=3 | eval\reports\observability_stack_latest.json |
| remote_ci_green | True | latest_run_id=22279367015, latest_run_conclusion=success | eval\reports\ci_remote_latest.json |
