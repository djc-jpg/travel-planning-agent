# trip-agent Web (Next.js 14)

Frontend console for `trip-agent` backend.

## Stack

- Next.js 14 + TypeScript + Tailwind
- shadcn/ui
- TanStack Query
- react-hook-form + zod

## Pages

- `/` plan form (`POST /plan`)
- `/chat` multi-turn chat (`POST /chat`) + structured local edit patch
- `/history` local history + server history/export
- `/diagnostics` health and diagnostics

## Env

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Example:

```env
API_BASE_URL=http://localhost:8000
```

## Run

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Backend endpoints used

- `POST /plan`
- `POST /chat`
- `GET /health`
- `GET /diagnostics`
- `GET /sessions/{session_id}/history`
- `GET /plans/{request_id}/export`

## Docker

```bash
docker build -t trip-agent-web ./frontend
docker run -p 3000:3000 -e API_BASE_URL=http://host.docker.internal:8000 trip-agent-web
```
