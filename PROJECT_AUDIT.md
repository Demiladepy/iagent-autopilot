# iAgent Autopilot — project audit

**Date:** May 27, 2026  
**Product name:** iAgent Autopilot (renamed from iAgent Sentinel)  
**Repo folder:** `iagent-sentinel/` (unchanged — internal package paths still use `sentinel`)

---

## Executive summary

You have a **submission-ready hackathon stack**: five-agent Python runtime, Next.js 14 workbench, simulator demos, API-key auth, Render/Vercel deploy path, and a polished landing page (Component Gallery + ai.work patterns). Your **background work** (API keys, MCP path, testnet wallet files) is wired for moving beyond pure simulator mode, but a few **config mismatches and security items** should be fixed before judges or GitHub.

| Area | Status |
|------|--------|
| Multi-agent pipeline | ✅ Complete |
| Dashboard / workbench | ✅ Complete |
| Simulator + demo scenarios | ✅ Complete |
| Production auth (API key) | ✅ Complete |
| Deploy docs (Render + Vercel) | ✅ Complete |
| Live MCP + testnet trading | 🟡 Config present; not fully aligned |
| Submission polish (video, screenshots, GitHub) | 🔴 Placeholders in README |
| Automated tests (local) | 🟡 14 tests exist; local pytest blocked by env plugin conflict |

---

## What you built (inventory)

### Runtime (`runtime/sentinel/`)

| Module | Role |
|--------|------|
| `main.py` | FastAPI app, REST, WebSocket, agent lifecycle, sim endpoints |
| `bus.py` | Async pub/sub (`event` → `proposal` → `verdict` → `execution` → `audit`) |
| `store.py` | SQLite persistence + journal migration |
| `mcp_client.py` | Stdio JSON-RPC to Injective MCP (28 tools) |
| `simulator.py` | Funding reversion, risk block, kill-switch scenarios |
| `security.py` | `SENTINEL_API_KEY`, `X-Sentinel-API-Key`, WS `api_key` query |
| `agents/watcher.py` | Groq + optional MCP reads |
| `agents/analyst.py` | Claude proposals |
| `agents/risk.py` | Deterministic limits + Groq veto |
| `agents/executor.py` | MCP writes only (gated by kill switch / dry run) |
| `agents/auditor.py` | Claude summaries + flags |
| `llm/` | Anthropic + Groq clients with stubs when keys missing |

### Dashboard (`dashboard/`)

| Route / area | Role |
|--------------|------|
| `/` | Landing — ai.work-style hero, workflow mockup, skills, metrics |
| `/dashboard` | Workbench — 3-column operator UI |
| `/api/proxy/*` | Server-side REST proxy + API key |
| `/api/ws-url` | Builds authenticated WebSocket URL |
| `components/sentinel/` | Gallery-aligned UI patterns |
| `lib/sentinel-store.ts` | Zustand + WS state |

### Ops & docs

| File | Role |
|------|------|
| `README.md` | Hackathon narrative, architecture, quickstart |
| `DEPLOY.md` | Render + Vercel env checklist |
| `render.yaml` | Render Blueprint |
| `COMPONENTS.md` | UI taxonomy |
| `docker-compose.yml` | Optional local Docker |

---

## Your local configuration (audit)

From `runtime/.env` and `injectivewalletinfo.json` (values not repeated here):

| Item | State | Notes |
|------|--------|------|
| `ANTHROPIC_API_KEY` | ✅ Set | Analyst, Auditor, strategy parse |
| `GROQ_API_KEY` | ✅ Set | Watcher, Risk sanity check |
| `MCP_SERVER_PATH` | ✅ Set | Points to built MCP server on disk |
| `INJECTIVE_NETWORK` | ✅ `testnet` | Correct for sprint |
| `SIMULATOR_MODE` | ✅ `true` | Demo-friendly; no live market required |
| `INJECTIVE_WALLET_ADDRESS` in `.env` | ⚠️ | **Does not match** `injective_address` in `injectivewalletinfo.json` |
| `INJECTIVE_WALLET_PASSWORD` in `.env` | ⚠️ | Placeholder text; json hints `inj-testnet-autopilot-2026` — align with MCP keystore password |
| `REQUIRE_API_KEY` | Not set (defaults false) | Fine for local dev |
| `DRY_RUN` | Not set | Defaults false — live executor could attempt writes when sim off |

**Action:** Pick **one** wallet: either import `injectivewalletinfo.json` key into MCP keystore (`wallet_import`) and use that `inj1...` + password in `.env`, or regenerate via MCP `wallet_generate` and update both files consistently.

---

## Security audit (critical)

| Risk | Severity | Recommendation |
|------|----------|----------------|
| `injectivewalletinfo.json` contains **mnemonic + private key** | 🔴 Critical | **Never commit.** Add to `.gitignore`. Rotate wallet if ever pushed. |
| `runtime/.env` has live API keys | 🔴 Critical | Already gitignored. Rotate Anthropic/Groq if exposed. |
| Two different `inj1` addresses | 🟡 Medium | Trades/balances will hit wrong account until fixed |
| Password placeholder in `.env` | 🟡 Medium | MCP `trade_open` will fail until real keystore password |

`.gitignore` covers `.env` but **not** `injectivewalletinfo.json` — fixed in this pass.

---

## Feature completeness

### Done

- [x] Five-agent orchestration with event bus
- [x] Decision timeline (accordion pipeline + raw JSON)
- [x] Kill switch + resume
- [x] Strategy editor + NL parse (Anthropic)
- [x] Demo scenarios (funding reversion, risk block, kill switch)
- [x] WebSocket live updates
- [x] Portfolio / positions panel (from `state_update`)
- [x] Audit stream
- [x] Explorer links for tx hashes
- [x] CORS + API key middleware
- [x] Health / ready probes for Render
- [x] Landing + workbench visual design

### Partial / optional

- [ ] Live Injective MCP on Render (needs Node + MCP on same host — use VPS or local)
- [ ] `docs/assets/*.png` screenshots referenced in README
- [ ] YouTube demo URL placeholder
- [ ] GitHub org/handle placeholders
- [ ] Rename repo folder `iagent-sentinel` → `iagent-autopilot` (optional; cosmetic)

### Internal naming (unchanged on purpose)

Code still uses `sentinel` for Python package, `SENTINEL_*` env vars, `sentinel-store.ts`, `@/components/sentinel`. **Product branding** is now **iAgent Autopilot** in UI and docs only — avoids a large breaking refactor.

---

## Deployment readiness

| Target | Ready? | Notes |
|--------|--------|------|
| Local demo | ✅ | `SIMULATOR_MODE=true`, keys in `runtime/.env`, `npm run dev` + `uvicorn` |
| Render API | ✅ | `render.yaml` + `DEPLOY.md`; set `ANTHROPIC`, `GROQ`, `CORS`, `SENTINEL_API_KEY` |
| Vercel dashboard | ✅ | `RUNTIME_API_URL` + matching `SENTINEL_API_KEY` |
| Live testnet on cloud | ❌ | MCP stdio + wallet not suited to Render free tier |

---

## Testing

| Check | Result |
|-------|--------|
| `npm run build` (dashboard) | ✅ Passed in prior session |
| `pytest tests/` | ✅ 14 passed in venv (`runtime/requirements-dev.txt`, `runtime/pytest.ini`) |
| Global Python without venv | ⚠️ Fails if third-party pytest plugins (e.g. `opik`) are installed — use venv |

```bash
cd runtime
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests/ -q
```

---

## Submission checklist (Injective Sprint)

| Item | Status |
|------|--------|
| Working demo (simulator) | ✅ |
| README explains AI + Injective | ✅ (update product name to Autopilot) |
| 90s video | 🔴 Placeholder URL |
| Screenshots in `docs/assets/` | 🔴 Likely missing |
| Public deploy URLs | 🔴 Your Render/Vercel URLs to add |
| No secrets in git | ⚠️ Fix `injectivewalletinfo.json` |

---

## Recommended next steps (priority order)

1. **Security:** Delete or gitignore `injectivewalletinfo.json`; rotate keys if repo was ever public.
2. **Wallet:** Align `.env` address + password with MCP keystore (one wallet).
3. **Record demo:** Simulator scenario + decision card + kill switch (90s).
4. **Deploy:** Render + Vercel with `SENTINEL_API_KEY` on both sides.
5. **README:** Replace `YOUR_VIDEO_ID`, `YOUR_ORG`, add live URLs.
6. **Optional:** `DRY_RUN=true` until you trust live execution.

---

## Architecture (current)

```
Landing (/) ──► Workbench (/dashboard)
                      │
                      ▼
              FastAPI :8000 (runtime)
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    EventBus    SQLite store   MCP (optional)
         │
    Watcher → Analyst → Risk → Executor → Auditor
         ▲
    Simulator (demo)
```

---

*This audit reflects the repo state after renaming the product to **iAgent Autopilot** in user-facing copy.*
