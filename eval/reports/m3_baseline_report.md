# Eval Report

- Generated at: 2026-02-19T20:48:05
- Cases: 15
- Pass: 10
- Average score: 0.90
- Pass rate: 67%

## Metric Pass Rates

| Metric | Pass Rate |
| --- | --- |
| budget_realism | 93% |
| constraint_satisfaction | 86% |
| duplication_backtracking | 64% |
| expected_properties_match | 64% |
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
| c03_shanghai_3d_family | WARN | 0.78 |
| c04_chengdu_4d_food_relaxed | PASS | 0.89 |
| c05_xian_3d_history_terracotta | PASS | 1.00 |
| c06_beijing_ultra_low_budget | PASS | 1.00 |
| c07_beijing_mobility_limit | PASS | 1.00 |
| c08_beijing_free_only | PASS | 0.89 |
| c09_beijing_1d_tight_must3 | WARN | 0.78 |
| c10_shanghai_3d_rain_museum | WARN | 0.78 |
| c11_chengdu_4d_no_spicy | WARN | 0.78 |
| c12_xian_3d_free_bias | WARN | 0.78 |
| c13_beijing_elderly_relaxed | PASS | 1.00 |
| c14_shanghai_2d_photo_night | PASS | 0.89 |
| c15_missing_requirements | PASS | 1.00 |

## Failed Checks

- `c03_shanghai_3d_family` duplication_backtracking: duplicates=True, cluster_switches=0, limit=3
- `c03_shanghai_3d_family` expected_properties_match: missing_backup_days=1
- `c04_chengdu_4d_food_relaxed` duplication_backtracking: duplicates=True, cluster_switches=0, limit=4
- `c08_beijing_free_only` expected_properties_match: non_free=故宫博物院,天安门城楼,中山公园,景山公园,北海公园
- `c09_beijing_1d_tight_must3` constraint_satisfaction: missing_must_visit=天安门广场,天安门城楼
- `c09_beijing_1d_tight_must3` expected_properties_match: missing_pois=天安门广场,天安门城楼
- `c10_shanghai_3d_rain_museum` duplication_backtracking: duplicates=True, cluster_switches=0, limit=3
- `c10_shanghai_3d_rain_museum` expected_properties_match: missing_backup_days=1
- `c11_chengdu_4d_no_spicy` duplication_backtracking: duplicates=True, cluster_switches=0, limit=4
- `c11_chengdu_4d_no_spicy` expected_properties_match: missing_pois=大熊猫基地
- `c12_xian_3d_free_bias` constraint_satisfaction: over_budget_without_warning
- `c12_xian_3d_free_bias` budget_realism: missing_budget_warning
- `c14_shanghai_2d_photo_night` duplication_backtracking: duplicates=True, cluster_switches=0, limit=2

## Top Failure Modes

- duplication_backtracking: 5
- expected_properties_match: 5
- constraint_satisfaction: 2
- budget_realism: 1

## Priority Suggestions

1. 优先加强地理聚类与去重，减少跨区折返。
2. 优先检查case预期字段与产品行为的一致性。
3. 优先补齐约束解析与硬约束执行（days/budget/must_visit/avoid）。
