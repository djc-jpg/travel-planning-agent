# 500+ 并发压测 Runbook

## 目标
- 在真实 HTTP 路径验证 500+ 并发容量，输出可追溯结论。
- 产出结构化报告（JSON + Markdown）用于发布证据。

## 快速执行（推荐）
```powershell
.\scripts\loadtest-500.ps1
```

该脚本会：
- 自动拉起本地 `uvicorn` 服务；
- 默认使用 `4` 个 worker（可通过 `-Workers` 覆盖）；
- 使用 `tools.loadtest_http` 发起并发压测；
- 输出 `eval/reports/loadtest_*.json` 与 `eval/reports/loadtest_*.md`。

## 手动执行
```powershell
$env:RATE_LIMIT_MAX = "100000"
$env:RATE_LIMIT_WINDOW = "60"

python -m tools.loadtest_http `
  --spawn-app `
  --spawn-port 18180 `
  --spawn-workers 4 `
  --base-url http://127.0.0.1:18180 `
  --total-requests 1000 `
  --concurrency 500 `
  --target-concurrency 500 `
  --target-success-rate 0.99 `
  --target-p95-ms 3000 `
  --request-payload '{""message"":""Plan a short trip""}'
```

## 结论字段
- `capacity_conclusion.meets_target`
- `capacity_conclusion.summary`
- `success_rate`
- `p95_latency_ms`
- `throughput_rps`

`meets_target=true` 表示在当前压测参数下，容量结论达到目标。

## 最近一次实测（2026-02-22）
- 报告：`eval/reports/loadtest_20260222_071446.json`
- 场景：500 并发、500 请求、4 workers、轻量请求体
- 结果：`success_rate=1.0`、`p95_latency_ms=1986.35`、`throughput_rps=132.61`
- 结论：在 `99%` 成功率 / `p95<=3000ms` 目标下通过（`meets_target=true`）

## Latest Run (2026-02-23)

- report: `eval/reports/loadtest_20260222_174222.json`
- scenario: 500 concurrency, 1000 requests, 4 workers, scripted env isolation (`STRICT_REQUIRED_FIELDS=true`, high rate-limit window)
- result: `success_rate=1.0`, `p95_latency_ms=1722.40`, `throughput_rps=224.73`
- verdict: `capacity_conclusion.meets_target=true`
