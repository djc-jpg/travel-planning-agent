# 外部依赖故障演练（限流 / 超时 / 降级）

## 目标
- 证明系统在依赖故障下行为可控（返回可解释错误或稳定降级），而不是崩溃。

## 执行
```powershell
.\scripts\dependency-fault-drill.ps1
```

等价命令：
```powershell
python -m app.deploy.dependency_fault_drill
```

## 场景覆盖
- `degraded_baseline`: 无外部 key、非严格模式下可稳定返回 DEGRADED。
- `strict_external_fail_fast`: 严格模式缺 key 时 fail-fast。
- `tool_timeout_fault`: 注入上游超时，验证受控失败（非 5xx 崩溃）。
- `tool_rate_limit_fault`: 注入上游 429，验证受控失败（非 5xx 崩溃）。
- `api_rate_limit_guard`: API 级限流返回 429。

## 报告
- 输出文件：`eval/reports/dependency_fault_drill_latest.json`
- 关键字段：
  - `passed`
  - `scenarios[].passed`
  - `scenarios[].detail`

## Latest Drill Result (2026-02-23)

- report: `eval/reports/dependency_fault_drill_latest.json`
- overall: `passed=true`
- scenario count: `5/5` passed
- highlights:
  - strict external without keys returns controlled fail-fast response
  - injected timeout and injected rate-limit faults return controlled business errors
  - API-level limiter returns `429` under burst traffic
