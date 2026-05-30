/** Copy & structure aligned with ai.work marketing patterns — adapted for Autopilot */

export const INTEGRATIONS = [
  "Injective MCP",
  "Claude",
  "Groq",
  "WebSocket",
  "SQLite",
  "FastAPI",
  "Next.js",
] as const;

export const AGENT_SKILLS = [
  {
    num: 1,
    title: "Market surveillance",
    body: "Watcher ingests funding, drawdown, and breakout signals from the event bus and Injective feeds.",
    tag: "Watcher · Groq",
  },
  {
    num: 2,
    title: "Trade proposals",
    body: "Analyst turns events into structured proposals with confidence, notional, and plain-English reasoning.",
    tag: "Analyst · Claude",
  },
  {
    num: 3,
    title: "Policy gate",
    body: "Risk enforces max notional, leverage, daily loss, and kill-switch — every trade needs approval.",
    tag: "Risk · Rules",
  },
  {
    num: 4,
    title: "MCP execution",
    body: "Executor is the only agent that calls Injective MCP write tools. No parallel SDK path.",
    tag: "Executor · MCP",
  },
  {
    num: 5,
    title: "Post-trade audit",
    body: "Auditor streams summaries and flags drift, slippage, and policy violations for judges.",
    tag: "Auditor · Claude",
  },
] as const;

export const ROI_METRICS = [
  {
    value: "5",
    suffix: " agents",
    title: "Multi-agent orchestration",
    body: "Supervisor-style pipeline: event → proposal → verdict → execution → audit.",
  },
  {
    value: "100%",
    suffix: "",
    title: "Decision receipts",
    body: "Every chain is persisted and visible in the dashboard timeline — nothing is a black box.",
  },
  {
    value: "1",
    suffix: " write path",
    title: "Governed execution",
    body: "Only Executor touches chain writes. Kill switch and risk limits are enforced by default.",
  },
] as const;

export const HOW_IT_WORKS = [
  {
    label: "01",
    title: "Text to trade plan",
    body: "Describe strategy in natural language. Risk limits are parsed and saved — your team sets policy, Autopilot enforces it.",
  },
  {
    label: "02",
    title: "Events become skills",
    body: "Each market event triggers the same five-agent pipeline. Resolutions are stored as auditable decision chains.",
  },
  {
    label: "03",
    title: "Autonomy with guardrails",
    body: "Approved proposals execute via MCP. Rejections, kill switch, and dry-run keep human control built in.",
  },
] as const;

export const PLATFORM_FEATURES = [
  {
    title: "Multi-agent orchestration",
    body: "Work splits across Watcher, Analyst, Risk, Executor, and Auditor with coordinated handoffs.",
  },
  {
    title: "Human-in-the-loop",
    body: "Kill switch, risk veto, and strategy limits — safe autonomy without blind execution.",
  },
  {
    title: "Governance & observability",
    body: "API keys, audit stream, explorer links, and SQLite journal for every decision.",
  },
] as const;
