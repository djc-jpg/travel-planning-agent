# Eval Report

- Generated at: 2026-02-19T20:59:24
- Cases: 15
- Pass: 15
- Average score: 0.99
- Pass rate: 100%

## Metric Pass Rates

| Metric | Pass Rate |
| --- | --- |
| budget_realism | 100% |
| constraint_satisfaction | 100% |
| duplication_backtracking | 93% |
| expected_properties_match | 100% |
| fact_verifiability | 100% |
| schema_requirement | 100% |
| schema_valid | 100% |
| status_match | 100% |
| structured_output_quality | 100% |
| travel_feasibility | 100% |

## Case Summary

| Case ID | Status | Score |
| --- | --- | --- |
| c01_beijing_4d_cny_peak | PASS | 1.00 |
| c02_beijing_4d_offseason_rain | PASS | 1.00 |
| c03_shanghai_3d_family | PASS | 1.00 |
| c04_chengdu_4d_food_relaxed | PASS | 1.00 |
| c05_xian_3d_history_terracotta | PASS | 1.00 |
| c06_beijing_ultra_low_budget | PASS | 1.00 |
| c07_beijing_mobility_limit | PASS | 1.00 |
| c08_beijing_free_only | PASS | 0.89 |
| c09_beijing_1d_tight_must3 | PASS | 1.00 |
| c10_shanghai_3d_rain_museum | PASS | 1.00 |
| c11_chengdu_4d_no_spicy | PASS | 1.00 |
| c12_xian_3d_free_bias | PASS | 1.00 |
| c13_beijing_elderly_relaxed | PASS | 1.00 |
| c14_shanghai_2d_photo_night | PASS | 1.00 |
| c15_missing_requirements | PASS | 1.00 |

## Failed Checks

- `c08_beijing_free_only` duplication_backtracking: duplicates=True, cluster_switches=1, limit=2

## Top Failure Modes

- duplication_backtracking: 1

## Priority Suggestions

1. 优先加强地理聚类与去重，减少跨区折返。
