"""Async stdio JSON-RPC client for the Injective MCP Server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from typing import Any, Literal, NotRequired, TypedDict

from sentinel.config import Settings

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "iagent-autopilot", "version": "0.1.0"}

DEFAULT_HANDSHAKE_TIMEOUT_SEC = 15.0
DEFAULT_TOOL_CALL_TIMEOUT_SEC = 30.0
DEFAULT_REQUEST_TIMEOUT_SEC = 120.0

MarketSymbol = Literal["BTC", "ETH", "INJ", "SOL", "ATOM"]
TradeSide = Literal["long", "short"]
LimitSide = Literal["buy", "sell"]

INJECTIVE_TOOLS = frozenset(
    {
        "wallet_generate",
        "wallet_import",
        "wallet_list",
        "wallet_remove",
        "market_list",
        "market_price",
        "account_balances",
        "account_positions",
        "token_metadata",
        "trade_open",
        "trade_close",
        "trade_open_eip712",
        "trade_close_eip712",
        "trade_limit_open",
        "trade_limit_orders",
        "trade_limit_close",
        "trade_limit_states",
        "transfer_send",
        "subaccount_deposit",
        "subaccount_withdraw",
        "bridge_withdraw_to_eth",
        "bridge_debridge_quote",
        "bridge_debridge_send",
        "bridge_debridge_inbound_quote",
        "bridge_debridge_inbound_send",
        "evm_broadcast",
        "authz_grant",
        "authz_revoke",
    }
)

# Write-capable MCP tools — only Executor may invoke these (never gated: read-only set).
MCP_WRITE_TOOLS = frozenset(
    {
        "wallet_generate",
        "wallet_import",
        "wallet_remove",
        "trade_open",
        "trade_close",
        "trade_open_eip712",
        "trade_close_eip712",
        "trade_limit_open",
        "trade_limit_close",
        "transfer_send",
        "subaccount_deposit",
        "subaccount_withdraw",
        "bridge_withdraw_to_eth",
        "bridge_debridge_send",
        "bridge_debridge_inbound_send",
        "evm_broadcast",
        "authz_grant",
        "authz_revoke",
    }
)

MCP_READ_TOOLS = INJECTIVE_TOOLS - MCP_WRITE_TOOLS


class WalletListArgs(TypedDict):
    pass


class MarketListArgs(TypedDict):
    pass


class MarketPriceArgs(TypedDict):
    symbol: str


class AccountBalancesArgs(TypedDict):
    address: str


class AccountPositionsArgs(TypedDict):
    address: str


class TradeOpenArgs(TypedDict):
    address: str
    password: str
    symbol: str
    side: TradeSide
    amount: str
    leverage: NotRequired[int]
    slippage: NotRequired[float]


class TradeCloseArgs(TypedDict):
    address: str
    password: str
    symbol: str
    slippage: NotRequired[float]


class TradeLimitOpenArgs(TypedDict):
    address: str
    password: str
    symbol: str
    side: LimitSide
    price: str
    quantity: str
    margin: str
    subaccountIndex: NotRequired[int]
    reduceOnly: NotRequired[bool]
    postOnly: NotRequired[bool]


class TransferSendArgs(TypedDict):
    address: str
    password: str
    recipient: str
    denom: str
    amount: str


class SubaccountDepositArgs(TypedDict):
    address: str
    password: str
    denom: str
    amount: str
    subaccountIndex: NotRequired[int]


class SubaccountWithdrawArgs(TypedDict):
    address: str
    password: str
    denom: str
    amount: str
    subaccountIndex: NotRequired[int]


class BridgeDebridgeQuoteArgs(TypedDict):
    srcDenom: str
    amount: str
    dstChain: str | int
    dstTokenAddress: str
    recipient: str


class MCPError(Exception):
    """Raised when an MCP request or tool call fails."""

    def __init__(
        self,
        message: str,
        *,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        response: Any = None,
        code: int | None = None,
        data: Any = None,
        error_detail: str | None = None,
    ) -> None:
        detail = error_detail or message
        parts = [message]
        if tool:
            parts.append(f"tool={tool}")
        if args is not None:
            parts.append(f"args={scrub_secrets(args)!r}")
        if error_detail and error_detail != message:
            parts.append(f"detail={error_detail}")
        if response is not None:
            parts.append(f"response={scrub_secrets(response)!r}")
        super().__init__(" ".join(parts))
        self.tool = tool
        self.tool_args = args
        self.response = response
        self.code = code
        self.data = data
        self.error_detail = detail


class MCPSpawnError(MCPError):
    """MCP subprocess failed to start (path, node, or spawn)."""


def scrub_secrets(value: Any) -> Any:
    """Redact password fields for logging and error messages."""
    if isinstance(value, dict):
        return {
            k: "***" if _is_secret_key(k) else scrub_secrets(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    return value


def _is_secret_key(key: str) -> bool:
    return key.lower() == "password"


class InjectiveMCPClient:
    """Stdio MCP client — spawns Node and speaks JSON-RPC 2.0 (line-delimited)."""

    def __init__(
        self,
        *,
        server_path: str,
        network: str = "testnet",
        node_executable: str = "node",
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT_SEC,
        tool_call_timeout: float = DEFAULT_TOOL_CALL_TIMEOUT_SEC,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SEC,
    ) -> None:
        self.server_path = server_path
        self.network = network
        self.node_executable = node_executable
        self.handshake_timeout = handshake_timeout
        self.tool_call_timeout = tool_call_timeout
        self.request_timeout = request_timeout

        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._request_id = 0
        self._write_lock = asyncio.Lock()
        self._stdout_buffer = ""
        self._initialized = False
        self._closed = False
        self._healthy = False
        self.tools: list[dict[str, Any]] = []

    @classmethod
    def from_settings(cls, settings: Settings) -> InjectiveMCPClient:
        if not settings.mcp_server_path:
            raise MCPSpawnError(
                "MCP_SERVER_PATH is not set. Add an absolute path to the built "
                "Injective MCP server script in runtime/.env (e.g. "
                ".../mcp-server/dist/mcp/server.js)."
            )
        return cls(
            server_path=settings.mcp_server_path,
            network=settings.injective_network,
            handshake_timeout=settings.mcp_handshake_timeout,
            tool_call_timeout=settings.mcp_tool_call_timeout,
            request_timeout=settings.mcp_request_timeout,
        )

    @property
    def is_connected(self) -> bool:
        return (
            not self._closed
            and self._process is not None
            and self._process.returncode is None
            and self._initialized
        )

    def is_healthy(self) -> bool:
        """True when the subprocess is up, handshake completed, and no crash/EOF."""
        return self._healthy and self.is_connected

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def start(self) -> None:
        if self._process is not None:
            raise MCPError("MCP client already started")
        await self._spawn_subprocess()
        try:
            await self._initialize()
            await self._fetch_tools()
            self._healthy = True
        except Exception:
            await self.stop()
            raise

    async def _spawn_subprocess(self) -> None:
        path = os.path.abspath(self.server_path)
        if not os.path.isfile(path):
            raise MCPSpawnError(
                f"MCP server script not found at: {path}\n"
                "Fix: set MCP_SERVER_PATH in runtime/.env to the absolute path of "
                "dist/mcp/server.js from https://github.com/InjectiveLabs/mcp-server "
                "(run `npm run build` in that repo first)."
            )

        node = self.node_executable
        if not shutil.which(node):
            raise MCPSpawnError(
                f"Node.js executable '{node}' was not found on PATH.\n"
                "Fix: install Node.js 18+ and ensure `node` is available, or set "
                "NODE_EXECUTABLE in the environment."
            )

        env = _base_env()
        env["INJECTIVE_NETWORK"] = self.network

        logger.info(
            "Starting Injective MCP server: %s %s (network=%s)",
            node,
            path,
            self.network,
        )
        try:
            self._process = await asyncio.create_subprocess_exec(
                node,
                path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MCPSpawnError(
                f"Failed to spawn MCP subprocess ({node} {path}): {exc}\n"
                "Fix: verify MCP_SERVER_PATH and that Node.js is installed."
            ) from exc
        except OSError as exc:
            raise MCPSpawnError(
                f"Failed to spawn MCP subprocess ({node} {path}): {exc}\n"
                "Fix: check file permissions and MCP_SERVER_PATH in runtime/.env."
            ) from exc

        if self._process.stdout is None or self._process.stderr is None:
            await self._terminate_process()
            raise MCPSpawnError(
                "MCP subprocess started but stdin/stdout pipes are unavailable."
            )

        self._closed = False
        self._healthy = False
        self._stdout_task = asyncio.create_task(
            self._read_stdout(), name="mcp-stdout-reader"
        )
        self._stderr_task = asyncio.create_task(
            self._read_stderr(), name="mcp-stderr-reader"
        )

    async def stop(self) -> None:
        if self._closed and self._process is None:
            return
        self._closed = True
        self._healthy = False

        for task in (self._stdout_task, self._stderr_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._stdout_task = None
        self._stderr_task = None

        self._fail_pending(MCPError("MCP client stopped"))

        await self._terminate_process()
        self._initialized = False

    async def _terminate_process(self) -> None:
        proc = self._process
        self._process = None
        if not proc:
            return
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
            try:
                await proc.stdin.wait_closed()
            except (AttributeError, ProcessLookupError, BrokenPipeError):
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("MCP process did not exit; killing")
            proc.kill()
            await proc.wait()
        if proc.returncode not in (None, 0):
            logger.warning("MCP process exited with code %s", proc.returncode)

    async def call(self, tool_name: str, args: dict[str, Any] | None = None) -> Any:
        if not self.is_healthy():
            raise MCPError(
                "MCP client is unhealthy (subprocess exited or crashed). "
                "Restart the runtime or check MCP_SERVER_PATH / Node logs.",
                tool=tool_name,
                args=args or {},
            )
        if tool_name not in INJECTIVE_TOOLS:
            raise MCPError(f"Unknown tool: {tool_name}", tool=tool_name, args=args or {})

        arguments = dict(args or {})
        safe_args = scrub_secrets(arguments)
        try:
            result = await self._request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                timeout=self.tool_call_timeout,
            )
        except MCPError as exc:
            if exc.tool is None:
                exc.tool = tool_name
                exc.tool_args = arguments
            if "timed out" in str(exc).lower():
                logger.error(
                    "MCP tools/call timed out after %.0fs: tool=%s args=%s",
                    self.tool_call_timeout,
                    tool_name,
                    safe_args,
                )
            raise

        return _parse_tool_result(result, tool=tool_name, args=arguments)

    async def wallet_list(self, args: WalletListArgs | None = None) -> Any:
        return await self.call("wallet_list", dict(args or {}))

    async def market_list(self, args: MarketListArgs | None = None) -> Any:
        return await self.call("market_list", dict(args or {}))

    async def market_price(self, args: MarketPriceArgs) -> Any:
        return await self.call("market_price", dict(args))

    async def account_balances(self, args: AccountBalancesArgs) -> Any:
        return await self.call("account_balances", dict(args))

    async def account_positions(self, args: AccountPositionsArgs) -> Any:
        return await self.call("account_positions", dict(args))

    async def trade_open(self, args: TradeOpenArgs) -> Any:
        return await self.call("trade_open", _normalize_trade_open(dict(args)))

    async def trade_close(self, args: TradeCloseArgs) -> Any:
        return await self.call("trade_close", dict(args))

    async def trade_limit_open(self, args: TradeLimitOpenArgs) -> Any:
        return await self.call("trade_limit_open", dict(args))

    async def transfer_send(self, args: TransferSendArgs) -> Any:
        return await self.call("transfer_send", dict(args))

    async def subaccount_deposit(self, args: SubaccountDepositArgs) -> Any:
        return await self.call("subaccount_deposit", dict(args))

    async def subaccount_withdraw(self, args: SubaccountWithdrawArgs) -> Any:
        return await self.call("subaccount_withdraw", dict(args))

    async def bridge_debridge_quote(self, args: BridgeDebridgeQuoteArgs) -> Any:
        return await self.call("bridge_debridge_quote", dict(args))

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self.call(name, arguments)

    async def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        try:
            while not self._closed:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    logger.warning("MCP stdout EOF — subprocess exited")
                    await self._on_process_exit()
                    break
                self._stdout_buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in self._stdout_buffer:
                    line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._handle_stdout_line(line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("MCP stdout reader failed: %s", exc)
            self._mark_unhealthy(MCPError(f"stdout reader failed: {exc}"))
        finally:
            remainder = self._stdout_buffer.strip()
            if remainder:
                self._handle_stdout_line(remainder)
                self._stdout_buffer = ""

    async def _read_stderr(self) -> None:
        assert self._process and self._process.stderr
        try:
            while not self._closed:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.info("[mcp-server stderr] %s", text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("MCP stderr reader ended: %s", exc)

    def _handle_stdout_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("MCP stdout non-JSON line skipped: %s", line[:200])
            return
        if not isinstance(message, dict):
            logger.debug("MCP stdout non-object skipped: %r", message)
            return
        self._dispatch(message)

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "method" in message and "id" not in message:
            logger.debug("MCP notification: %s", message.get("method"))
            return

        msg_id = message.get("id")
        if msg_id is None:
            return

        fut = self._pending.pop(msg_id, None)
        if fut is None:
            logger.debug("MCP response for unknown id=%s", msg_id)
            return
        if fut.done():
            return

        if "error" in message:
            err = message["error"]
            fut.set_exception(
                MCPError(
                    err.get("message", "Unknown JSON-RPC error"),
                    response=message,
                    code=err.get("code"),
                    data=err.get("data"),
                    error_detail=str(err.get("message", "")),
                )
            )
        else:
            fut.set_result(message.get("result", {}))

    async def _on_process_exit(self) -> None:
        code = self._process.returncode if self._process else None
        self._mark_unhealthy(MCPError(f"MCP subprocess exited (code={code})"))

    def _mark_unhealthy(self, exc: BaseException) -> None:
        self._healthy = False
        self._initialized = False
        self._closed = True
        self._fail_pending(exc)

    def _fail_pending(self, exc: BaseException) -> None:
        pending = list(self._pending.values())
        self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(exc)

    async def _send_raw(
        self,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if self._closed or not self._process or not self._process.stdin:
            raise MCPError("MCP process not running")
        if self._process.returncode is not None:
            raise MCPError(f"MCP process already exited (code={self._process.returncode})")

        msg_id = payload.get("id")
        fut: asyncio.Future[dict[str, Any]] | None = None
        if msg_id is not None:
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self._pending[msg_id] = fut

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            async with self._write_lock:
                self._process.stdin.write(line.encode("utf-8"))
                await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            if msg_id is not None:
                self._pending.pop(msg_id, None)
            self._mark_unhealthy(MCPError(f"Failed to write to MCP stdin: {exc}"))
            raise MCPError(f"Failed to write to MCP stdin: {exc}") from exc

        if fut is None:
            return {}

        effective_timeout = timeout if timeout is not None else self.request_timeout
        try:
            return await asyncio.wait_for(fut, timeout=effective_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            method = payload.get("method", "?")
            raise MCPError(
                f"MCP request timed out after {effective_timeout}s: {method}",
                response={"method": method, "id": msg_id},
            )

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        await self._send_raw(payload)

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        msg_id = self._next_id()
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        return await self._send_raw(payload, timeout=timeout)

    async def _initialize(self) -> None:
        try:
            result = await self._request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
                timeout=self.handshake_timeout,
            )
        except MCPError as exc:
            if "timed out" in str(exc).lower():
                await self._terminate_process()
                raise MCPError(
                    f"MCP initialize did not complete within {self.handshake_timeout}s. "
                    "The Node MCP server may be hung or misconfigured. "
                    "Fix: verify MCP_SERVER_PATH, run the server manually with `node <path>`, "
                    "or increase MCP_HANDSHAKE_TIMEOUT."
                ) from exc
            raise
        except asyncio.TimeoutError:
            await self._terminate_process()
            raise MCPError(
                f"MCP initialize did not complete within {self.handshake_timeout}s. "
                "The Node MCP server may be hung or misconfigured. "
                "Fix: verify MCP_SERVER_PATH, run the server manually with `node <path>`, "
                "or increase MCP_HANDSHAKE_TIMEOUT."
            ) from None

        server_info = result.get("serverInfo", {})
        logger.info(
            "MCP handshake complete: %s v%s",
            server_info.get("name", "unknown"),
            server_info.get("version", "?"),
        )
        await self._notify("notifications/initialized")
        self._initialized = True

    async def _fetch_tools(self) -> None:
        result = await self._request("tools/list", timeout=self.request_timeout)
        self.tools = result.get("tools", [])
        names = {t.get("name") for t in self.tools if isinstance(t, dict)}
        logger.info("MCP tools/list: %d tools available", len(self.tools))
        missing = INJECTIVE_TOOLS - names
        if missing:
            logger.warning("Expected MCP tools not reported: %s", sorted(missing))


def _parse_tool_result(
    result: dict[str, Any],
    *,
    tool: str,
    args: dict[str, Any],
) -> Any:
    if result.get("isError"):
        detail = _extract_error_detail(result)
        raise MCPError(
            f"Tool returned error: {tool}",
            tool=tool,
            args=args,
            response=result,
            error_detail=detail,
        )

    if isinstance(result.get("error"), str):
        raise MCPError(
            f"Tool result error field: {tool}",
            tool=tool,
            args=args,
            response=result,
            error_detail=result["error"],
        )

    content = result.get("content", [])
    if not content:
        return result

    texts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    combined = "\n".join(t for t in texts if t)
    if not combined:
        return result

    try:
        parsed = json.loads(combined)
    except json.JSONDecodeError:
        return combined

    if isinstance(parsed, dict) and parsed.get("error"):
        raise MCPError(
            f"Tool payload error: {tool}",
            tool=tool,
            args=args,
            response=parsed,
            error_detail=str(parsed.get("error")),
        )
    return parsed


def _extract_error_detail(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        text = content[0].get("text", "")
        if text:
            try:
                payload = json.loads(text)
                if isinstance(payload, dict) and payload.get("error"):
                    return str(payload["error"])
            except json.JSONDecodeError:
                return text
    return "unknown tool error"


def _normalize_trade_open(args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args)
    if "amount" not in out and "notional" in out:
        notional = out.pop("notional")
        out["amount"] = str(notional) if not isinstance(notional, str) else notional
    elif "amount" in out and not isinstance(out["amount"], str):
        out["amount"] = str(out["amount"])
    return out


def _base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if isinstance(v, str)}


_mcp_singleton: InjectiveMCPClient | None = None


async def get_mcp_client(settings: Settings) -> InjectiveMCPClient | None:
    global _mcp_singleton
    if settings.dry_run or not settings.mcp_server_path:
        return None
    if _mcp_singleton is not None and not _mcp_singleton.is_healthy():
        logger.warning("MCP client unhealthy — skipping MCP until runtime restart")
        return None
    if _mcp_singleton is None:
        _mcp_singleton = InjectiveMCPClient.from_settings(settings)
        await _mcp_singleton.start()
    return _mcp_singleton


def mcp_client_is_healthy() -> bool | None:
    """Return None if no client started, else live health from the singleton."""
    if _mcp_singleton is None:
        return None
    return _mcp_singleton.is_healthy()


async def shutdown_mcp_client() -> None:
    global _mcp_singleton
    if _mcp_singleton:
        await _mcp_singleton.stop()
        _mcp_singleton = None


async def _smoke_test() -> None:
    from sentinel.config import get_settings

    settings = get_settings()
    if not settings.mcp_server_path:
        print("Set MCP_SERVER_PATH in .env to run smoke test", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    client = InjectiveMCPClient.from_settings(settings)
    try:
        await client.start()
        print(f"Tools loaded: {len(client.tools)}")
        markets = await client.call("market_list", {})
        print(json.dumps(markets, indent=2)[:500])
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(_smoke_test())
