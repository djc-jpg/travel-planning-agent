# Product Acceptance Checklist

## 1) 快速冒烟（默认降级模式）
- 目标：确认用户可见输出可读、无 debug 泄露、run fingerprint 完整。
- 命令：
```powershell
python -m tools.product_acceptance
```
- 期望：
  - `smoke_passed=true`
  - `smoke.status=done`
  - `smoke.hidden_debug_ok=true`
  - `smoke.run_fingerprint.run_mode` 存在（常见为 `DEGRADED`）

## 2) 严格模式 fail-fast 检查
- 目标：`STRICT_EXTERNAL_DATA=true` 且外部 key 缺失时必须失败。
- 命令：
```powershell
python -m app.deploy.preflight --env-file .env.prerelease --skip-smoke
```
- 期望：
  - 若 `STRICT_EXTERNAL_DATA=true` 且未配置 `AMAP_API_KEY`，报告包含 `strict_external_data=FAIL`。
  - 若 `STRICT_EXTERNAL_DATA=true` 且已配置 `AMAP_API_KEY`，`strict_external_data=PASS`。

## 3) 全量验收（评测 + gate）
- 目标：确保本次改动可发布。
- 命令：
```powershell
python -m tools.product_acceptance --full
```
- 期望：
  - `full_passed=true`
  - `eval.returncode=0`
  - `release_gate.returncode=0`

## 4) 真实 key 手工复核（上线前）
- 配置真实 `DASHSCOPE_API_KEY` / `AMAP_API_KEY` 后，在前端生成至少 3 个城市案例。
- 重点核查：
  - 行程摘要是否可读（无机器串）
  - 不出现停车场/上车点等基础设施 POI
  - 预算总览与单点门票文案一致（非一律 0 元）
  - `run_fingerprint` 能解释当前模式（`REALTIME` 或 `DEGRADED`）

## 5) 产品级扩展验收（容量/观测/持久化/故障演练）
- 500+ 并发压测：
```powershell
$env:RATE_LIMIT_MAX="100000"
$env:RATE_LIMIT_WINDOW="60"
.\scripts\loadtest-500.ps1 -Workers 4
```
- SLO 校验：
```powershell
.\scripts\slo-drill.ps1 -Profile degraded
```
- 持久化备份恢复演练：
```powershell
.\scripts\persistence-drill.ps1
```
- 外部依赖故障演练：
```powershell
.\scripts\dependency-fault-drill.ps1
```

### 5.1 通过标准
- 压测报告 `capacity_conclusion.meets_target=true`
- `dependency_fault_drill_latest.json` 中 `passed=true`
- `persistence_drill_latest.json` 中 `passed=true`
- 关键前端 E2E 全通过（`npm run e2e`）

### 5.2 当前状态（2026-02-22）
- 故障演练：已通过（`eval/reports/dependency_fault_drill_latest.json`）
- 持久化演练：已通过（`eval/reports/persistence_drill_latest.json`）
- 前端 E2E：已通过（3/3）
- 500 并发容量目标：已通过（`eval/reports/loadtest_20260222_071446.json`，`success_rate=1.0`, `p95=1986.35ms`）
- SLO 校验：降级档已通过（`eval/reports/slo_latest.json`）；实时档需在真实外部依赖流量环境复核
- 观测栈连通性：已通过（`eval/reports/observability_stack_latest.json`）
- realtime SLO 复核：已完成（`eval/reports/slo_realtime_latest.json`），当前未达标（`p95=7785.01ms`, `l3_ratio=0.35`, `l0_ratio=0.0`）
