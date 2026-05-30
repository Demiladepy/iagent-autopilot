# Deploy: Render + Vercel (hackathon)

You do **not** need Docker. Run locally with Python + Node, deploy the API to **Render** and the dashboard to **Vercel**.

## 1. Render — Python runtime

1. Push this repo to GitHub.
2. [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint** (or **Web Service**).
3. Connect the repo. If using Blueprint, Render reads `render.yaml` at the repo root.
4. Set **Root Directory** to `runtime` (if not using Blueprint).
5. **Build command:** `pip install -r requirements.txt`
6. **Start command:** `uvicorn sentinel.main:app --host 0.0.0.0 --port $PORT`
7. **Health check path:** `/health` (liveness). Optional readiness probe: `/ready` (MCP + store + agents when not in simulator-only mode).

### Required env vars (Render → Environment)

| Variable | Example | Notes |
|----------|---------|--------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Analyst + Auditor + strategy parse |
| `GROQ_API_KEY` | `gsk_...` | Watcher + Risk |
| `SENTINEL_API_KEY` | *(generate)* | Same value you set on Vercel |
| `REQUIRE_API_KEY` | `true` | |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | Your Vercel URL (comma-separate localhost if needed) |
| `SIMULATOR_MODE` | `true` | Demo scenarios without live market |
| `DRY_RUN` | `true` | No on-chain writes (recommended on Render) |
| `SENTINEL_DB_PATH` | `/tmp/sentinel.db` | Ephemeral disk on free tier — fine for demo |

Optional (live MCP + testnet — usually **not** on Render free tier):

| Variable | Notes |
|----------|--------|
| `MCP_SERVER_PATH` | Needs Node + built MCP server on the same machine; use a VPS instead of Render for real MCP |
| `INJECTIVE_WALLET_ADDRESS` | Only if MCP is running |

Copy your Render URL, e.g. `https://iagent-autopilot-api.onrender.com`.

## 2. Vercel — Next.js dashboard

1. [Vercel](https://vercel.com/) → **Add New Project** → import the same repo.
2. Set **Root Directory** to `dashboard`.
3. Framework preset: **Next.js** (auto-detected).

### Required env vars (Vercel → Settings → Environment Variables)

| Variable | Value |
|----------|--------|
| `RUNTIME_API_URL` | `https://iagent-autopilot-api.onrender.com` (your Render URL) |
| `SENTINEL_API_KEY` | Same secret as on Render |

Deploy. Open your `*.vercel.app` URL.

REST calls go through `/api/proxy/*` (server-side, with API key). WebSocket uses `/api/ws-url` (server builds `wss://...?api_key=...`).

## 3. Wire CORS

On Render, set:

```env
CORS_ORIGINS=https://your-project.vercel.app,http://localhost:3000
```

Redeploy Render after changing CORS.

## 4. Local dev (no Docker)

```bash
# Terminal 1 — API
cd runtime
cp .env.example .env   # fill keys; leave REQUIRE_API_KEY=false for easy local dev
pip install -r requirements.txt
uvicorn sentinel.main:app --reload --port 8000

# Terminal 2 — dashboard
cd dashboard
cp .env.local.example .env.local
# RUNTIME_API_URL=http://127.0.0.1:8000
npm install && npm run dev
```

Open http://localhost:3000 → **Run scenario: Funding Reversion**.

## Why not Docker for the hackathon?

Docker is optional for judges who want one command locally. For submission, **Render + Vercel** is free, fast to ship, and matches how most hackathon demos are hosted.

## Optional: Docker locally

```bash
docker compose up --build
```

Only if you prefer containers on your laptop — not required for deployment.
