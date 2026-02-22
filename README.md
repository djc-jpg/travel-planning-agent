# trip-agent — AI 旅行行程规划助手

基于 **LangGraph** 状态机 + **Pydantic** 强类型 + 规则验证器的旅行行程规划 Agent。

## 功能特色

- 🧠 **LLM 智能模式**：接入通义千问（DashScope）/ OpenAI，自动生成旅行文案、智能解析用户意图
- 🔄 **模板回退**：无 API Key 时全离线运行，用规则模板生成行程
- 🗺️ **高德地图集成**：真实 POI 搜索 + 路线规划（需配置 `AMAP_API_KEY`）
- 📚 **可校验景点事实层（北京）**：内置 `app/data/poi_beijing.json`，包含门票、预约、开放时间、闭馆规则
- 🧭 **可插拔 Routing Provider**：`real`（地图API）/`fixture`（默认，可复现）双模式
- 💰 **预算真实性模型**：门票 + 市内交通 + 餐饮最低值拆分，输出 `budget_breakdown`
- 🧱 **可执行时间轴**：交通时长 + 安检/排队缓冲 + 用餐窗口，避免不可能衔接
- 🏙️ **多城市支持**：内置 10 城 120+ 景点数据（北京/上海/杭州/成都/西安/广州/南京/重庆/长沙/厦门）
- 🤖 **LLM 兜底**：本地无数据的城市（如丽江、三亚）由 LLM 实时生成真实景点
- 💬 **多轮对话**：自然追问补充信息，支持 CLI 和 API 两种交互方式
- 🛠️ **结构化局部编辑**：支持 `replace_stop` / `add_stop` / `remove_stop` / `adjust_time` / `lunch_break`
- 📤 **导出能力**：支持行程导出 `JSON` 与 `Markdown`
- ✅ **自动验证修复**：时间/距离/预算/节奏校验 + 最多 3 轮自动修复

## 架构总览

```
用户输入
  │
  ▼
┌─────────┐    缺参    ┌──────────┐
│  Intake │──────────▶│  Clarify │──▶ 等待用户补充
│ (LLM/正则)          └──────────┘
└────┬────┘
     │ 完整
     ▼
┌──────────┐
│ Retrieve │ ← 高德API / 本地数据 / LLM生成
└────┬─────┘
     ▼
┌──────────────┐
│ Planner Core │ ← 近邻贪心 + 时间块分配
└────┬─────────┘
     ▼
┌──────────────┐
│ Planner NLG  │ ← LLM详细旅行指南 / 模板回退
└────┬─────────┘
     ▼
┌──────────┐    有 issue    ┌────────┐
│ Validate │──────────────▶│ Repair │──┐
└────┬─────┘               └────────┘  │
     │ 无 issue / 超限          │       │
     ▼                         ▼       │
┌──────────┐           Validate ◀──────┘
│ Finalize │           (最多 3 次循环)
└──────────┘
     │
     ▼
  🗺️ 格式化行程单
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

| 环境变量 | 用途 | 必需？ |
|---------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云通义千问 LLM 服务 | 否（无则用模板模式） |
| `AMAP_API_KEY` | 高德地图 POI + 路线 | 否（无则用本地数据） |
| `OPENAI_API_KEY` | OpenAI LLM 服务（替代方案） | 否 |
| `API_BEARER_TOKEN` | 后端 API Bearer 鉴权令牌 | 生产/预发布建议必填 |
| `ALLOW_UNAUTHENTICATED_API` | 允许无鉴权访问 API（仅本地调试） | 否（默认本地 `true`，预发布 `false`） |
| `STRICT_EXTERNAL_DATA` | 强制外部数据 fail-fast（无 key 或不可用即失败） | 否 |
| `LLM_MODEL` | 指定模型名（默认 qwen3-coder-plus） | 否 |
| `ROUTING_PROVIDER` | `fixture`/`real`/`auto`（默认 `auto`） | 否 |
| `FOOD_MIN_PER_PERSON_PER_DAY` | 餐饮最低预算（默认 `60`） | 否 |
| `DEFAULT_SPRING_FESTIVAL_DATE` | 春节场景默认起始日（默认 `2026-02-17`） | 否 |
| `API_BASE_URL` | 前端服务端代理转发到后端的地址 | 否（默认 `http://localhost:8000`） |

**优先级**：`DASHSCOPE_API_KEY` > `OPENAI_API_KEY` > `LLM_API_KEY`

### 3. CLI — 单轮规划

```bash
python -m app.cli "我想去北京玩3天，喜欢历史和美食"
```

输出示例：
```
🗺️ 北京 3日旅行行程
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 第 1 天
  ⏰ 09:00-11:30 | 📍 故宫博物院
     🚌 步行 → 约15分钟
     💬 故宫是中国最大的古代宫殿建筑群...
  ⏰ 12:00-13:30 | 📍 南锣鼓巷
     ...
```

### 4. CLI — 多轮交互

```bash
python -m app.cli
# 跟随引导输入需求，支持逐步补充信息
```

### 5. API 服务

```bash
uvicorn app.api.main:app --reload
```

端点：
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/metrics` | 运行指标快照 |
| GET | `/diagnostics` | 诊断信息（需 `ENABLE_DIAGNOSTICS=true` + `DIAGNOSTICS_TOKEN`） |
| POST | `/plan` | 一次性规划 `{"message": "..."}` |
| POST | `/chat` | 多轮对话 `{"session_id": "xxx", "message": "..."}` |
| GET | `/sessions` | 会话列表（需 API 鉴权） |
| GET | `/sessions/{session_id}/history` | 会话历史（需 API 鉴权） |
| GET | `/plans/{request_id}/export` | 导出 JSON（需 API 鉴权） |
| GET | `/plans/{request_id}/export?format=markdown` | 导出 Markdown（需 API 鉴权） |

鉴权说明：
- 默认采用 fail-closed 策略：未配置 `API_BEARER_TOKEN` 且 `ALLOW_UNAUTHENTICATED_API=false` 时，API 返回 `503`。
- 本地开发可使用 `.env.example` 默认值（`ALLOW_UNAUTHENTICATED_API=true`）。
- 预发布/生产请设置 `API_BEARER_TOKEN`，并保持 `ALLOW_UNAUTHENTICATED_API=false`。

### 6. Docker 部署

```bash
docker build -t trip-agent .
docker run -p 8000:8000 --env-file .env trip-agent
```

### 7. 评测

```bash
python -m app.eval.run_eval
python -m eval.beijing_4d_cny
python -m eval.run --cases eval/cases.json --out eval/reports --tag baseline
python -m eval.run --cases eval/cases.json --out eval/reports --tag improved
python -m eval.compare --base eval/reports/baseline_report.json --new eval/reports/improved_report.json --out eval/reports/compare.md
```

`python -m eval.beijing_4d_cny` 会输出北京4日春节专项评测，并写入：
`app/eval/reports/eval_report.md`

`python -m eval.run` 会输出通用客户场景评测，写入：
- `eval/reports/<tag>_report.json`
- `eval/reports/<tag>_report.md`
- `eval/reports/latest_report.json`
- `eval/reports/latest_report.md`

评测case定义在 `eval/cases.json`，每条case包含：
- `id`
- `user_request`
- `constraints`
- `context`
- `expected_properties`
- `human_notes`（可选）

人工抽检标准见：`docs/eval_rubric.md`

`eval.run` 评分解释：
- `PASS`：case score `>= 0.85`
- `WARN`：`0.60 <= score < 0.85`
- `FAIL`：`< 0.60`

新增用例步骤：
1. 在 `eval/cases.json` 新增一条对象，至少包含 `id/user_request/constraints/context/expected_properties`
2. 运行 `python -m eval.run --cases eval/cases.json --out eval/reports --tag <tag>`
3. 查看 `eval/reports/<tag>_report.md` 的失败指标与证据

### 8. 测试

```bash
pytest tests/ -v
```

## 支持城市

### 内置数据（120+ POI）
北京 · 上海 · 杭州 · 成都 · 西安 · 广州 · 南京 · 重庆 · 长沙 · 厦门

### LLM 兜底生成
配置 LLM 后，任意城市均可生成行程（如丽江、三亚、大理等），LLM 会实时生成当地真实景点数据。

## 模块职责

| 模块 | 职责 |
|------|------|
| `app/domain/` | Pydantic 领域模型（TripConstraints, UserProfile, POI, Itinerary 等） |
| `app/application/` | 单入口编排（`plan_trip`）、图状态、局部编辑补丁 |
| `app/application/graph/` | 核心节点与工作流（intake/clarify/retrieve/validate/repair/finalize） |
| `app/services/` | API/CLI 服务层（执行规划、历史查询、导出格式化） |
| `app/adapters/` | 外部能力适配器（高德 POI/路线、天气、日历）与工具工厂 |
| `app/tools/` | 工具输入输出接口与共享协议层 |
| `app/planner/` | 行程排程、路由可信度、预算与现实性计算 |
| `app/repair/` | 行程修复与重排策略 |
| `app/trust/` | 事实来源分类、置信度评分、约束满足度 |
| `app/persistence/` | 持久化模型与仓储实现（SQLite/内存） |
| `app/infrastructure/` | LLM 工厂、缓存、限流、会话存储等基础设施 |
| `app/api/` | FastAPI API（鉴权、限流、中间件、契约） |
| `app/observability/` | 结构化日志、指标采集与诊断快照 |
| `app/agent/` | 兼容层（保留旧命名空间，转发到 `app.application`） |
| `app/eval/` | 回归评测与发布门禁 |

## 核心设计

### 北京4日春节专项能力

- 景点事实从 `app/data/poi_beijing.json` 读取，不再凭空生成票价/预约规则
- 覆盖核心景点事实：故宫、天安门广场/城楼、天坛、景山、北海、中山公园、正阳门城楼、老舍故居、明城墙遗址公园、龙潭公园
- 春节场景自动注入高峰缓冲（安检/排队）与错峰建议
- 日内时间轴包含交通、缓冲、午餐窗口（`meal_windows`）
- 预算输出包含 `budget_breakdown` 与最低可行预算提示

### 双模式运行

| 模式 | 条件 | 能力 |
|------|------|------|
| **LLM 模式** | 设置了 API Key | 智能意图解析、自然语言追问、详细旅行指南文案、任意城市支持 |
| **模板模式** | 无 API Key | 正则解析、模板追问、短文案、仅内置城市 |

### 验证器 Issue Codes

| Code | 含义 | Severity |
|------|------|----------|
| `OVER_TIME` | 每天行程超时 | high |
| `TOO_MUCH_TRAVEL` | 路上时间过多 | high |
| `OVER_BUDGET` | 总费用超预算 | high |
| `BUDGET_UNREALISTIC` | 预算明显不现实 | medium |
| `PACE_MISMATCH` | 景点数量不匹配节奏 | medium |
| `TRAVEL_TIME_INVALID` | 点间交通时间异常 | high |
| `MISSING_FACTS` | 景点事实字段缺失 | high |
| `ROUTE_BACKTRACKING` | 日内折返/片区切换偏多 | medium |
| `DUPLICATE_POI_DAY` | 同日重复安排景点 | high |
| `MISSING_BACKUP` | 缺少备选方案 | low |

### 修复策略阶梯

1. 替换同主题近距离 POI
2. 删减低优先级景点
3. 改交通方式（提示成本上升）
4. 降级输出（写 assumptions）

## 目录结构

```
app/
├── cli.py                    # CLI 入口
├── api/main.py               # FastAPI 入口（/plan /chat /sessions /export）
├── application/              # 单入口编排与工作流
│   ├── plan_trip.py
│   ├── itinerary_edit.py
│   └── graph/
├── services/                 # plan/history/export 服务层
├── adapters/                 # 外部 API 适配器与工具工厂
├── infrastructure/           # 缓存/限流/LLM 工厂/会话存储
├── planner/                  # 排程、预算、路线可信度
├── repair/                   # 修复策略
├── trust/                    # 事实分类 + 置信度
├── persistence/              # repository + sqlite backend
├── domain/                   # 领域模型
├── tools/                    # tool interfaces / shared schemas
├── data/                     # 内置 POI 与路由 fixture
├── observability/            # 指标与日志
└── agent/                    # 旧路径兼容层（逐步收敛中）
frontend/                     # Next.js 控制台
tests/                        # pytest 测试套件
docs/                         # runbook / 架构快照 / 验收清单
tools/                        # 质量门禁与验收脚本
```

## 扩展

- **更多城市**：编辑 `app/data/poi_v1.json` 添加 POI，或配置 `AMAP_API_KEY` 使用高德在线搜索
- **LLM 提供商**：设置 `LLM_BASE_URL` + `LLM_API_KEY` 接入任意 OpenAI 兼容端点
- **检索增强（可选）**：安装 `faiss-cpu` + `sentence-transformers`（`pip install -e .[retrieval]`）用于实验型语义召回
- **前端对接**：API 已启用 CORS，可直接从浏览器/前端应用调用

## Pre-release Quick Start

1. Copy prerelease env template:

```bash
cp .env.prerelease.example .env.prerelease
```

2. Start prerelease stack and run preflight checks:

```powershell
.\scripts\prerelease.ps1
```

3. Stop prerelease stack:

```powershell
.\scripts\prerelease-down.ps1
```

4. If Docker is not installed, run local prerelease checks:

```powershell
.\scripts\prerelease-local.ps1
```

`prerelease-local.ps1` defaults to in-memory backend fallback for single-machine checks.
Use `-StrictRedis` when you want Redis connectivity to be mandatory.

## Guarded CI + Rollout Drill

Architecture/runtime guard commands:

```bash
python tools/check_import_boundaries.py
python tools/check_single_entrypoint.py
python -m app.eval.run_eval
PYTHONPATH=. python eval/run.py --cases eval/cases.json --out eval/reports --tag baseline
```

Pre-release canary + rollback drill (Docker Compose):

```powershell
.\scripts\prerelease-rollout.ps1
```

Emergency rollback to stable flags (`ENGINE_VERSION=v1`, `STRICT_REQUIRED_FIELDS=false`):

```powershell
.\scripts\prerelease-rollback.ps1
```

## Product Quick Start (Stage 1)

This repo now provides a default `docker-compose.yml` for product-style local startup.

1. Copy local env template:

```bash
cp .env.example .env
```

2. Start backend + frontend:

```bash
docker compose up --build
```

3. Open services:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`

### Run modes

- No external keys configured: system starts in degraded mode and still generates itineraries.
- With real keys configured (`AMAP_API_KEY` + optional LLM key): system can run realtime providers.
- With `STRICT_EXTERNAL_DATA=true`: missing/unavailable required external data must fail fast (no silent fallback).
- API auth:
  - local default: `ALLOW_UNAUTHENTICATED_API=true`
  - prerelease/production: set `API_BEARER_TOKEN` and keep `ALLOW_UNAUTHENTICATED_API=false`
- Frontend uses server-side proxy (`/api/backend/...`) and forwards to `API_BASE_URL` (no public token required in browser env).

### Validation commands

```bash
python -m ruff check --select E9,F app tests tools eval
pytest -q -p no:cacheprovider
python -m app.eval.run_eval
python -m eval.release_gate_runner
python -m tools.release_summary
python -m tools.product_acceptance --full
```
