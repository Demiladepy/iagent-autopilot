"""Unit tests for sentinel.mcp_client (fake Node MCP subprocess)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import unittest
from pathlib import Path

from sentinel.mcp_client import (
    MCPError,
    MCPSpawnError,
    InjectiveMCPClient,
    scrub_secrets,
    shutdown_mcp_client,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_MCP = FIXTURES / "fake_mcp_server.mjs"


def _require_node() -> None:
    if not shutil.which("node"):
        raise unittest.SkipTest("node not on PATH")


def _fake_client(
    behavior: str,
    *,
    handshake_timeout: float = 15.0,
    tool_call_timeout: float = 30.0,
) -> InjectiveMCPClient:
    _require_node()
    os.environ["FAKE_MCP_BEHAVIOR"] = behavior
    return InjectiveMCPClient(
        server_path=str(FAKE_MCP),
        network="testnet",
        handshake_timeout=handshake_timeout,
        tool_call_timeout=tool_call_timeout,
        request_timeout=60.0,
    )


class MCPClientHappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await shutdown_mcp_client()
        self.client = _fake_client("happy")
        os.environ["FAKE_MCP_BEHAVIOR"] = "happy"

    async def asyncTearDown(self) -> None:
        await self.client.stop()
        await shutdown_mcp_client()

    async def test_handshake_and_tools_list(self) -> None:
        await self.client.start()
        self.assertTrue(self.client.is_healthy())
        self.assertGreater(len(self.client.tools), 0)

    async def test_tools_call_json_payload(self) -> None:
        await self.client.start()
        result = await self.client.call("market_list", {})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("tool"), "market_list")
        self.assertTrue(result.get("ok"))

    async def test_plain_text_result(self) -> None:
        await self.client.stop()
        self.client = _fake_client("plain_text")
        await self.client.start()
        result = await self.client.call("market_price", {"symbol": "BTC"})
        self.assertIsInstance(result, str)
        self.assertIn("plain result", result)

    async def test_dirty_stdout_interleaved(self) -> None:
        await self.client.stop()
        self.client = _fake_client("dirty_stdout")
        await self.client.start()
        result = await self.client.call("wallet_list", {})
        self.assertTrue(result.get("ok"))


class MCPClientFailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await shutdown_mcp_client()

    async def test_spawn_bad_path(self) -> None:
        client = InjectiveMCPClient(
            server_path="/nonexistent/mcp/server.js",
            handshake_timeout=2.0,
            tool_call_timeout=2.0,
        )
        with self.assertRaises(MCPSpawnError) as ctx:
            await client.start()
        msg = str(ctx.exception)
        self.assertIn("MCP_SERVER_PATH", msg)
        self.assertIn("not found", msg.lower())

    async def test_handshake_timeout(self) -> None:
        client = _fake_client("slow_init", handshake_timeout=0.4, tool_call_timeout=2.0)
        with self.assertRaises(MCPError) as ctx:
            await client.start()
        self.assertIn("initialize", str(ctx.exception).lower())
        await client.stop()

    async def test_tool_call_timeout(self) -> None:
        client = _fake_client("hang_call", handshake_timeout=5.0, tool_call_timeout=0.5)
        await client.start()
        with self.assertRaises(MCPError) as ctx:
            await client.call("market_list", {})
        self.assertIn("timed out", str(ctx.exception).lower())
        await client.stop()

    async def test_subprocess_crash_marks_unhealthy(self) -> None:
        client = _fake_client("crash_on_call", handshake_timeout=5.0, tool_call_timeout=5.0)
        await client.start()
        self.assertTrue(client.is_healthy())
        with self.assertRaises(MCPError):
            await client.call("market_list", {})
        await asyncio.sleep(0.3)
        self.assertFalse(client.is_healthy())

    async def test_json_rpc_error_response(self) -> None:
        client = _fake_client("error_rpc")
        await client.start()
        with self.assertRaises(MCPError) as ctx:
            await client.call("market_list", {})
        self.assertIn("simulated", str(ctx.exception).lower())
        await client.stop()

    async def test_tool_error_payload(self) -> None:
        client = _fake_client("error_tool")
        await client.start()
        with self.assertRaises(MCPError) as ctx:
            await client.call("market_list", {})
        self.assertIsNotNone(ctx.exception.error_detail)
        await client.stop()

    async def test_unhealthy_call_rejected(self) -> None:
        client = _fake_client("happy")
        await client.start()
        client._healthy = False
        with self.assertRaises(MCPError) as ctx:
            await client.call("market_list", {})
        self.assertIn("unhealthy", str(ctx.exception).lower())
        await client.stop()


class MCPClientConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await shutdown_mcp_client()

    async def test_five_concurrent_calls_route_correctly(self) -> None:
        client = _fake_client("happy")
        await client.start()
        tools = ["market_list", "market_price", "wallet_list", "account_balances", "account_positions"]
        tasks = [
            client.call(t, {"symbol": "BTC"} if t == "market_price" else {"address": "inj1test"})
            for t in tools
        ]
        results = await asyncio.gather(*tasks)
        self.assertEqual(len(results), 5)
        returned_tools = {r.get("tool") for r in results}
        self.assertEqual(returned_tools, set(tools))
        ids = {r.get("echo_id") for r in results}
        self.assertEqual(len(ids), 5)
        await client.stop()


class MCPClientScrubbingTests(unittest.TestCase):
    def test_scrub_secrets_dict(self) -> None:
        scrubbed = scrub_secrets({"address": "inj1x", "password": "super-secret"})
        self.assertEqual(scrubbed["password"], "***")
        self.assertEqual(scrubbed["address"], "inj1x")

    def test_password_never_in_timeout_log(self) -> None:
        _require_node()

        async def _run() -> str:
            client = _fake_client("hang_call", tool_call_timeout=0.3)
            await client.start()
            log_buffer: list[str] = []

            class _Capture(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    log_buffer.append(record.getMessage())

            handler = _Capture()
            handler.setLevel(logging.ERROR)
            mcp_logger = logging.getLogger("sentinel.mcp_client")
            mcp_logger.addHandler(handler)
            mcp_logger.setLevel(logging.ERROR)
            try:
                with self.assertRaises(MCPError):
                    await client.call(
                        "trade_open",
                        {
                            "address": "inj1test",
                            "password": "TOP_SECRET_PASSWORD",
                            "symbol": "BTC",
                            "side": "long",
                            "amount": "10",
                        },
                    )
            finally:
                mcp_logger.removeHandler(handler)
                await client.stop()
            return "\n".join(log_buffer)

        log_text = asyncio.run(_run())
        self.assertIn("trade_open", log_text)
        self.assertIn("***", log_text)
        self.assertNotIn("TOP_SECRET_PASSWORD", log_text)


if __name__ == "__main__":
    unittest.main()
