# Observability Stack (Prometheus/Grafana/Tracing/SLO)

## 组件
- Prometheus 抓取：`/metrics/prometheus`
- Grafana 看板：`deploy/observability/grafana/dashboards/trip-agent-overview.json`
- 告警规则：`deploy/observability/alert_rules.yml`
- 追踪上下文：`traceparent` / `X-Trace-ID` 响应头
- SLO 校验：`tools/slo_check.py`

## 启动
```powershell
.\scripts\observability-up.ps1
```

前提：
- 后端服务需要先运行在宿主机 `http://localhost:8000`（Prometheus 默认抓取 `host.docker.internal:8000`）。
- 本机 Docker 引擎可用（`docker version` 可正常返回）。

访问：
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

停止：
```powershell
.\scripts\observability-down.ps1
```

## SLO 校验
推荐一键演练（自动打流 + 校验）：
```powershell
.\scripts\slo-drill.ps1 -Profile degraded
```

基于实时 `/metrics` 直接校验：
```powershell
python -m tools.slo_check --base-url http://127.0.0.1:8000 --profile auto
```

说明：
- 先用 `/plan` 或前端页面制造实际流量，再执行 SLO 校验，否则指标会接近 0。
- 在无真实外部 key 的降级环境中，`l0_ratio` 目标可能失败（属于预期），生产环境需在真实流量下评估。
- `--profile degraded` 用于本地降级验收；`--profile realtime` 用于生产实时能力验收。

基于离线快照：
```powershell
python -m tools.slo_check --metrics-json path\to\metrics_snapshot.json
```

目标定义文件：`deploy/observability/slo_objectives.json`。

## 最近一次连通性验收（2026-02-22）
- 报告：`eval/reports/observability_stack_latest.json`
- 结果：
  - Prometheus `ready=true`
  - `trip-agent-backend` scrape target `health=up`
  - 告警规则已加载（3 条）
  - Grafana 健康检查 `database=ok`
