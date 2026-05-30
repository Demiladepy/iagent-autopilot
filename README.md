# iAgent Autopilot

> Autonomous multi-agent trading on Injective, with receipts.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Next.js 14](https://img.shields.io/badge/Next.js-14-black)
![MCP](https://img.shields.io/badge/MCP-Injective%20Server-emerald)
![Injective Testnet](https://img.shields.io/badge/network-Injective%20Testnet-10B981)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**[▶ Watch the 90-second demo](https://www.youtube.com/watch?v=YOUR_VIDEO_ID)** · *[Replace with your YouTube link before submission]*

<p align="center">
  <a href="https://www.youtube.com/watch?v=YOUR_VIDEO_ID">
    <img src="docs/assets/dashboard-decision-card.png" alt="iAgent Autopilot — annotated decision card showing event → proposal → risk → execution → audit" width="720" />
  </a>
  <br />
  <em>One decision, fully explained: market event → Analyst proposal → Risk verdict → on-chain execution → Auditor summary.</em>
</p>

## What this is

The [Injective MCP Server](https://github.com/InjectiveLabs/mcp-server) lets any AI agent trade perpetual futures via natural language. **iAgent Autopilot** is the production layer on top: a five-agent autonomous trading system with hard risk limits, persistent memory, and a full audit trail for every decision.

Built for the **Injective Solo AI Builder Sprint** (May 2026).

**Project status:** see [PROJECT_AUDIT.md](PROJECT_AUDIT.md) for a full audit of what’s done, config gaps, and submission checklist.

## Why this matters

Today, an Injective AI agent is one Claude instance with MCP tools. That is powerful — but unsafe for autonomous use:

- **No memory** between sessions
- **No coordination** between specialized concerns (analysis, risk, execution)
- **No deterministic guardrails** — one bad prompt and your account is empty
- **No transparency** — you cannot replay why a trade happened

Autopilot fixes all four. It is the layer that turns the MCP Server from *“Claude can trade”* into **“a swarm of agents trades within rules you set, and shows you every decision.”**

## How AI is used

| Agent | Model | Role |
|---|---|---|
| **Watcher** | Groq Llama 3.3 70B | High-frequency market polling, event detection, human-readable event descriptions |
| **Analyst** | Claude Sonnet 4.5 | Deep reasoning over events + strategy + history → structured trade proposals |
| **Risk** | Groq Llama 3.3 70B | Separate-brain sanity check on Analyst proposals, layered on **deterministic** limit enforcement |
| **Executor** | *(no LLM)* | Calls Injective MCP Server tools only after Risk approval |
| **Auditor** | Claude Sonnet 4.5 | Plain-English explanation of every decision after the fact |

**Anthropic for reasoning, Groq for latency.** Each agent has one narrow job — that is how the system stays safe.

Strategy limits can also be parsed from natural language via **Claude Haiku 4.5** in the dashboard (`POST /strategy/parse`), so operators never have to hand-edit JSON.

## How Injective is integrated

Autopilot sits on top of the official **[Injective MCP Server](https://github.com/InjectiveLabs/mcp-server)**. Every chain interaction — opening positions, closing, adjusting, bridging, checking balances — flows through MCP tool calls over stdio JSON-RPC. There is no parallel chain SDK in this repo; we inherit everything the MCP Server supports out of the box.

The **Executor** is the only component allowed to call write tools (`trade_open`, `trade_close`, `adjust`, etc.). That restriction is architectural: other agents never receive an MCP client. Read-only snapshots (`account_positions`, `account_balances`, `market_list`) are used by the Watcher and API layer.

Testnet by default (`INJECTIVE_NETWORK=testnet`). Transaction links in the dashboard resolve to the correct [Injective explorer](https://testnet.explorer.injective.network/) for your network.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Next.js 14 Dashboard (:3000)                        │
│   Strategy · Kill switch · Agent grid · Decision timeline · Demo scenarios  │
│         REST /api/proxy/*  ·  WebSocket ws://runtime:8000/ws                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                    FastAPI Runtime (:8000) · SQLite store                   │
│                         asyncio EventBus (pub/sub)                          │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
     ┌──────────────┐    event     ┌──────────────┐   proposal   ┌──────────┐
     │   Watcher    │─────────────►│   Analyst    │─────────────►│   Risk   │
     │ Groq + MCP   │              │ Claude Sonnet│              │ rules +  │
     │   poll       │              │              │              │ Groq veto│
     └──────────────┘              └──────────────┘              └────┬─────┘
            ▲                                                        │ verdict
            │ sim_inject                                             ▼ approved
     ┌──────────────┐                                         ┌──────────────┐
     │  Simulator   │                                         │   Executor   │──► Injective MCP
     │  (demo)      │                                         │  (no LLM)    │    trade_open / close
     └──────────────┘                                         └──────┬───────┘
                                                                     │ execution
                                                                     ▼
                                                              ┌──────────────┐
                                                              │   Auditor    │
                                                              │ Claude Sonnet│
                                                              │ audit + flags│
                                                              └──────────────┘
```

**Pipeline:** `event` → `proposal` → `verdict` → `execution` → `audit` — each step persisted and streamed live to the dashboard.

## Quickstart (local — no Docker)

### Prerequisites

- Python 3.11+
- Node 18+
- [Anthropic](https://console.anthropic.com/) and [Groq](https://console.groq.com/) API keys
- *(Optional)* [Injective MCP Server](https://github.com/InjectiveLabs/mcp-server) — only for live testnet trading, not required for the simulator demo

### Run locally

```bash
git clone https://github.com/YOUR_ORG/iagent-sentinel.git
cd iagent-sentinel

# API
cd runtime
cp .env.example .env
# Add ANTHROPIC_API_KEY, GROQ_API_KEY. Leave SIMULATOR_MODE=true, REQUIRE_API_KEY=false for local dev.
pip install -r requirements.txt
uvicorn sentinel.main:app --reload --port 8000

# Dashboard (new terminal)
cd dashboard
cp .env.local.example .env.local
# RUNTIME_API_URL=http://127.0.0.1:8000
npm install && npm run dev
```

1. Open [http://localhost:3000](http://localhost:3000) · API docs [http://localhost:8000/docs](http://localhost:8000/docs)
2. Set your strategy in plain English → **Parse** → **Save**
3. Click **Run scenario: Funding Reversion** and watch all five agents on the decision timeline

### Deploy (hackathon): Render + Vercel

**You do not need Docker.** Host the FastAPI runtime on [Render](https://render.com) and the Next.js dashboard on [Vercel](https://vercel.com).

See **[DEPLOY.md](DEPLOY.md)** for step-by-step env vars (`RUNTIME_API_URL`, `SENTINEL_API_KEY`, `CORS_ORIGINS`, etc.).

| Service | Hosts | Root folder |
|---------|--------|-------------|
| API + agents + WebSocket | Render | `runtime/` |
| Dashboard | Vercel | `dashboard/` |

Use `SIMULATOR_MODE=true` and `DRY_RUN=true` on Render for the judge demo (no Node MCP process required). Live Injective MCP fits better on a VPS; the hackathon path is simulator + LLM pipeline.

### Security

When `SENTINEL_API_KEY` is set (recommended on Render/Vercel), protected routes need `X-Sentinel-API-Key`. The Vercel proxy and `/api/ws-url` add the key server-side — it is not baked into the client JS bundle.

Public probes only: `GET /health`, `GET /ready`.

<details>
<summary>Optional: Docker on your laptop</summary>

```bash
docker compose up --build
```

Convenience only — not used for Render/Vercel deployment.

</details>

## What you'll see in the demo

<p align="center">
  <img src="docs/assets/dashboard-overview.png" alt="Dashboard overview — agent fleet, decision timeline, kill switch, and demo controls" width="720" />
</p>

| # | What to look at |
|---|-----------------|
| 1 | **Agent fleet** — five cards with live status dots and last action (updates over WebSocket) |
| 2 | **Decision card** — full pipeline: market event → Analyst proposal (confidence bar) → Risk approve/reject → Executor tx link → Auditor summary + flags |
| 3 | **Kill switch** — one click halts execution; Watcher and Risk keep running |
| 4 | **Strategy editor** — NL text → structured limits (notional, leverage, daily loss, markets) |
| 5 | **Demo controls** — Funding Reversion, Risk Block, Kill Switch scenarios without waiting for live market moves |

**[▶ 90-second walkthrough (YouTube)](https://www.youtube.com/watch?v=YOUR_VIDEO_ID)**

<!-- Optional embed once the video is live:
[![Demo](https://img.youtube.com/vi/YOUR_VIDEO_ID/0.jpg)](https://www.youtube.com/watch?v=YOUR_VIDEO_ID)
-->

## Project layout

| Path | Purpose |
|---|---|
| `runtime/sentinel/` | FastAPI app, five agents, SQLite store, MCP client, simulator |
| `dashboard/` | Next.js 14 operator UI |
| `render.yaml` | Render Blueprint for the API |
| `DEPLOY.md` | Render + Vercel deployment guide |
| `docker-compose.yml` | Optional local Docker only |

## Roadmap (potential for future contributions)

- **Strategy marketplace** — publish your strategy as an importable JSON file
- **Backtesting** — replay historical events through the agent pipeline
- **Multi-account orchestration** — run Autopilot against N accounts with N strategies
- **Custom agents** — drop-in Python files in `/agents/custom/` get auto-registered
- **Mainnet hardening** — additional guardrails for live trading

## License

MIT. See [LICENSE](LICENSE) if present, or MIT terms apply to this repository.

## Built by

**[@YOUR_HANDLE](https://github.com/YOUR_HANDLE)** — for the Injective Solo AI Builder Sprint, May 2026.

Tagging: [@injective](https://x.com/injective) · [@NinjaLabsHQ](https://x.com/NinjaLabsHQ) · [@NinjaLabsCN](https://x.com/NinjaLabsCN)
