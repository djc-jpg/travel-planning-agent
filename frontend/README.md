# trip-agent Web (Next.js 14)

专业前端控制台，完整对接 `trip-agent` FastAPI 后端。

## 技术栈

- Next.js 14 + TypeScript + Tailwind CSS
- shadcn/ui 组件风格
- TanStack Query（请求状态）
- react-hook-form + zod（表单与校验）

## 页面

- `/` Plan：结构化表单 -> 调用 `POST /plan`，展示行程并支持导出
- `/chat` Chat：会话列表 + 多轮对话（`POST /chat`）+ 行程预览侧栏
- `/history` History：本地保存最近 10 次规划结果，可恢复/删除
- `/diagnostics` Diagnostics：检测 `/health` 和 `/diagnostics` 可用性与延迟

## 环境变量

复制 `.env.example` 为 `.env.local`：

```bash
cp .env.example .env.local
```

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 本地启动

```bash
npm install
npm run dev
```

访问 `http://localhost:3000`。

## 对接后端

确保后端启动：

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

前端通过 `NEXT_PUBLIC_API_BASE_URL` 访问：

- `POST /plan`
- `POST /chat`
- `GET /health`
- `GET /diagnostics`

## 错误处理策略

- 超时：`AbortController` 超时中断
- `429`：提示“请求过于频繁”
- `422`：提示“参数校验失败”
- `5xx`：提示“服务暂时不可用”
- 网络错误：提示“无法连接后端”

## Docker

```bash
docker build -t trip-agent-web ./frontend
docker run -p 3000:3000 -e NEXT_PUBLIC_API_BASE_URL=http://host.docker.internal:8000 trip-agent-web
```

## 目录结构

```text
frontend/
  app/
  components/
  hooks/
  lib/
  providers/
  Dockerfile
```
