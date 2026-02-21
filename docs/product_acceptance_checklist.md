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
python -m app.deploy.preflight --json
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
