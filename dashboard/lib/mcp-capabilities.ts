/**
 * Static Injective MCP tool catalog for the dashboard Capabilities panel.
 * Display-only — must match runtime/sentinel/mcp_client.py INJECTIVE_TOOLS (28 tools).
 */

export type McpToolCategoryId =
  | "wallet"
  | "markets"
  | "account"
  | "trading"
  | "transfers"
  | "subaccounts"
  | "bridging"
  | "evm";

export type McpCapabilityTool = {
  name: string;
  /** Used by agents in the standard demo / public simulator pipeline */
  exercisedInDemo: boolean;
};

export type McpToolCategory = {
  id: McpToolCategoryId;
  label: string;
  tools: McpCapabilityTool[];
};

/** Tools touched in the live demo path (Watcher, Risk, Analyst, Executor dry-run / transfer_send). */
const DEMO_EXERCISED = new Set([
  "market_list",
  "market_price",
  "account_balances",
  "account_positions",
  "trade_open",
  "trade_close",
  "transfer_send",
]);

function tool(name: string): McpCapabilityTool {
  return { name, exercisedInDemo: DEMO_EXERCISED.has(name) };
}

export const MCP_CAPABILITIES_TAGLINE =
  "Autopilot's governed pipeline can route any Injective MCP capability through the same surveil → propose → risk-gate → execute → audit flow.";

export const MCP_TOOL_COUNT = 28;

export const MCP_TOOL_CATEGORIES: McpToolCategory[] = [
  {
    id: "wallet",
    label: "Wallet",
    tools: [
      tool("wallet_generate"),
      tool("wallet_import"),
      tool("wallet_list"),
      tool("wallet_remove"),
    ],
  },
  {
    id: "markets",
    label: "Markets",
    tools: [tool("market_list"), tool("market_price"), tool("token_metadata")],
  },
  {
    id: "account",
    label: "Account",
    tools: [tool("account_balances"), tool("account_positions")],
  },
  {
    id: "trading",
    label: "Trading",
    tools: [
      tool("trade_open"),
      tool("trade_close"),
      tool("trade_open_eip712"),
      tool("trade_close_eip712"),
      tool("trade_limit_open"),
      tool("trade_limit_orders"),
      tool("trade_limit_close"),
      tool("trade_limit_states"),
    ],
  },
  {
    id: "transfers",
    label: "Transfers",
    tools: [tool("transfer_send")],
  },
  {
    id: "subaccounts",
    label: "Subaccounts",
    tools: [tool("subaccount_deposit"), tool("subaccount_withdraw")],
  },
  {
    id: "bridging",
    label: "Bridging",
    tools: [
      tool("bridge_withdraw_to_eth"),
      tool("bridge_debridge_quote"),
      tool("bridge_debridge_send"),
      tool("bridge_debridge_inbound_quote"),
      tool("bridge_debridge_inbound_send"),
    ],
  },
  {
    id: "evm",
    label: "EVM & Authz",
    tools: [tool("evm_broadcast"), tool("authz_grant"), tool("authz_revoke")],
  },
];

export function countDemoExercisedTools(): number {
  return MCP_TOOL_CATEGORIES.reduce(
    (n, cat) => n + cat.tools.filter((t) => t.exercisedInDemo).length,
    0
  );
}
