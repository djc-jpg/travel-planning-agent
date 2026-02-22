# Remote CI Evidence (latest branch runs)

- generated_at: 2026-02-22T22:16:00.0150301+08:00
- repository: djc-jpg/travel-planning-agent
- branch: wip/p0-sync-20260222
- latest_run_id: 22278380739
- latest_run_conclusion: failure
- latest_all_green: False

## Run 22278380739
- title: ci: retry dependency fault drill to reduce transient flake
- status/conclusion: completed / failure
- sha: 41ec37e51dd1858d59227b40ba41fe607bd1696c
- url: https://github.com/djc-jpg/travel-planning-agent/actions/runs/22278380739
| job | conclusion |
| --- | --- |
| secret-scan | success |
| operational-drills | failure |
| frontend | success |
| test (3.13) | success |
| test (3.11) | success |
| frontend-e2e | success |
| docker | skipped |

## Run 22278059018
- title: chore: run realtime slo review and capture remote ci evidence pipeline
- status/conclusion: completed / failure
- sha: 785fa50767b227a3fc1117fa1f9ed17aff12d0b9
- url: https://github.com/djc-jpg/travel-planning-agent/actions/runs/22278059018
| job | conclusion |
| --- | --- |
| secret-scan | success |
| frontend | success |
| operational-drills | failure |
| test (3.11) | success |
| test (3.13) | success |
| frontend-e2e | success |
| docker | skipped |

