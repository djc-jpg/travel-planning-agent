# Remote CI Evidence (latest branch runs)

- generated_at: 2026-02-22T23:21:26.9331061+08:00
- repository: djc-jpg/travel-planning-agent
- branch: wip/p0-sync-20260222
- latest_run_id: 22279367015
- latest_run_conclusion: success
- latest_all_green: True

## Run 22279367015
- title: drill: accept strict fail-fast 500 in CI and compact evidence
- status/conclusion: completed / success
- sha: 4431b8aa9d9acb9676ec5d18419658e6c30be133
- url: https://github.com/djc-jpg/travel-planning-agent/actions/runs/22279367015
| job | conclusion |
| --- | --- |
| secret-scan | success |
| frontend | success |
| operational-drills | success |
| test (3.13) | success |
| test (3.11) | success |
| frontend-e2e | success |
| docker | success |

## Run 22278870433
- title: docs: archive latest remote ci run evidence
- status/conclusion: completed / failure
- sha: db7da5056ab55724a3c3a38448561e73486217ac
- url: https://github.com/djc-jpg/travel-planning-agent/actions/runs/22278870433
| job | conclusion |
| --- | --- |
| secret-scan | success |
| frontend | success |
| test (3.11) | success |
| test (3.13) | success |
| operational-drills | failure |
| frontend-e2e | success |
| docker | skipped |

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

