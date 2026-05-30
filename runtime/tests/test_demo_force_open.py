"""Integration-ish unit test: /demo/force-open triggers normal pipeline (mock MCP)."""

from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

from tests.base import SentinelClientTestCase


class _FakeMCP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def is_healthy(self) -> bool:
        return True

    async def call(self, tool: str, args: dict) -> dict:
        self.calls.append((tool, dict(args)))
        if tool == "transfer_send":
            return {"txHash": "REALTXHASH123"}
        return {"ok": True}


class DemoForceOpenTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Custom startup (base class forces DRY_RUN=true). We want DRY_RUN=false here.
        import tempfile

        from sentinel.config import get_settings

        os.environ["SENTINEL_DB_PATH"] = tempfile.mktemp(suffix="-sentinel-test.db")
        os.environ["SIMULATOR_MODE"] = "true"
        os.environ["DRY_RUN"] = "false"
        os.environ["DEMO_REAL_TX"] = "true"
        os.environ["DEMO_TX_AMOUNT"] = "0.1"
        os.environ["DEMO_TX_RECIPIENT"] = "inj10an2mpnknpmnxdu2csmx8dt4mztvh8czgj0z3d"
        os.environ["INJECTIVE_WALLET_ADDRESS"] = "inj1h07rx97gmplmsthnqt3r4ntte95vy96mxpvhnp"
        os.environ["INJECTIVE_WALLET_PASSWORD"] = "pw"
        os.environ["MCP_SERVER_PATH"] = "C:/fake/server.js"
        os.environ["SENTINEL_API_KEY"] = ""
        os.environ["REQUIRE_API_KEY"] = "false"
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
        os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
        os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

        get_settings.cache_clear()
        cls._client_ctx = cls.make_client()
        cls.client = cls._client_ctx.__enter__()

    def test_force_open_produces_execution_via_normal_path(self) -> None:
        import sentinel.main as main

        fake = _FakeMCP()
        with patch("sentinel.agents.executor.get_mcp_client", AsyncMock(return_value=fake)), patch(
            "sentinel.agents.risk.groq_client.risk_sanity_check",
            AsyncMock(return_value=(True, "ok", 1.0)),
        ):
            res = self.client.post("/demo/force-open")
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertTrue(body.get("ok"))
            proposal_id = body.get("proposal_id")
            self.assertTrue(proposal_id)

            # Wait for async agents to process (risk → executor).
            execution: dict | None = None
            for _ in range(60):
                execution = asyncio.run(
                    main.state.store.get_execution_for_proposal(str(proposal_id))
                )
                if execution:
                    break
                time.sleep(0.2)

            self.assertIsNotNone(execution, "Execution did not appear in time")
            assert isinstance(execution, dict)
            self.assertEqual(execution.get("status"), "success")
            self.assertEqual(execution.get("tool_called"), "transfer_send")
            self.assertEqual(execution.get("tx_hash"), "REALTXHASH123")
            self.assertFalse(str(execution.get("tx_hash")).startswith("dry-run-"))

            tools = [t for (t, _a) in fake.calls]
            self.assertIn("transfer_send", tools)


if __name__ == "__main__":
    unittest.main()

