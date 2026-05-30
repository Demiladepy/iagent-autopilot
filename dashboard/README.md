# iAgent Autopilot Dashboard

Next.js 14 operator UI for the Autopilot runtime.

## Development

```bash
# Terminal 1 — runtime (from repo root)
cd runtime && pip install -e . && uvicorn sentinel.main:app --reload

# Terminal 2 — dashboard
cp .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). REST is proxied via `/api/proxy/*` → `RUNTIME_API_URL`. WebSocket connects to `ws://<hostname>:8000/ws` (override with `NEXT_PUBLIC_WS_URL`).

## Production (Docker)

Built from repo root: `docker compose up --build`. Dashboard at port 3000, API at 8000.
