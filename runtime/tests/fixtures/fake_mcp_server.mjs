/**
 * Fake Injective MCP server for unit tests (stdio JSON-RPC).
 * Set FAKE_MCP_BEHAVIOR: happy | slow_init | hang_call | crash_after_init |
 *   crash_on_call | error_rpc | error_tool | plain_text | dirty_stdout
 */
import readline from "node:readline";

const behavior = process.env.FAKE_MCP_BEHAVIOR || "happy";
let callCount = 0;

const TOOLS = [
  "wallet_list",
  "market_list",
  "market_price",
  "account_balances",
  "account_positions",
  "trade_open",
  "trade_close",
];

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function okResult(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function errResult(id, message) {
  send({
    jsonrpc: "2.0",
    id,
    error: { code: -32000, message },
  });
}

if (behavior === "dirty_stdout") {
  process.stdout.write("[fake-mcp] boot log line (not json)\n");
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const { id, method, params } = msg;

  if (method && id === undefined) {
    return;
  }

  if (method === "initialize") {
    if (behavior === "slow_init") {
      return;
    }
    okResult(id, {
      protocolVersion: "2024-11-05",
      serverInfo: { name: "fake-mcp", version: "0.0.1" },
      capabilities: {},
    });
    if (behavior === "crash_after_init") {
      setImmediate(() => process.exit(1));
    }
    return;
  }

  if (method === "tools/list") {
    okResult(id, {
      tools: TOOLS.map((name) => ({ name, description: `fake ${name}` })),
    });
    return;
  }

  if (method === "tools/call") {
    callCount += 1;
    const tool = params?.name ?? "unknown";
    const args = params?.arguments ?? {};

    if (behavior === "hang_call") {
      return;
    }
    if (behavior === "crash_on_call" && callCount >= 1) {
      setImmediate(() => process.exit(2));
      return;
    }
    if (behavior === "error_rpc") {
      errResult(id, "simulated rpc failure");
      return;
    }
    if (behavior === "error_tool") {
      okResult(id, {
        isError: true,
        content: [{ type: "text", text: JSON.stringify({ error: "tool rejected" }) }],
      });
      return;
    }
    if (behavior === "plain_text") {
      okResult(id, {
        content: [{ type: "text", text: `plain result for ${tool}` }],
      });
      return;
    }

    const payload = {
      echo_id: id,
      tool,
      args_keys: Object.keys(args),
      ok: true,
    };
    okResult(id, {
      content: [{ type: "text", text: JSON.stringify(payload) }],
    });
    return;
  }

  if (id !== undefined) {
    okResult(id, {});
  }
});
