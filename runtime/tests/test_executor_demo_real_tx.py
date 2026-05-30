"""Unit tests: demo real tx branch in Executor (transfer_send substitute)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from sentinel.bus import EventBus
from sentinel.schemas import Proposal, RiskVerdict
from sentinel.store import SentinelStore


class _FakeMCP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def is_healthy(self) -> bool:
        return True

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        self.calls.append((tool, dict(args)))
        if tool == "transfer_send":
            return {"txHash": "ABC123REALTXHASH"}
        if tool == "market_list":
            return []
        raise RuntimeError(f"unexpected tool: {tool}")


class ExecutorDemoRealTxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bus = EventBus()
        self.db_path = tempfile.mktemp(suffix="-executor-demo.db")
        self.store = SentinelStore(self.db_path)
        await self.store.connect()

    async def asyncTearDown(self) -> None:
        await self.store.close()

    async def test_demo_real_tx_calls_transfer_send_and_persists_real_hash(self) -> None:
        from sentinel.agents import executor as ex
        from sentinel.config import Settings

        config = Settings.model_construct(
            anthropic_api_key="x",
            groq_api_key="x",
            simulator_mode=False,
            dry_run=False,
            demo_real_tx=True,
            demo_tx_amount="0.1",
            demo_tx_recipient="inj10an2mpnknpmnxdu2csmx8dt4mztvh8czgj0z3d",
            injective_network="testnet",
            injective_wallet_address="inj1h07rx97gmplmsthnqt3r4ntte95vy96mxpvhnp",
            injective_wallet_password="pw",
            mcp_server_path="C:/fake/server.js",
            sentinel_db_path=self.db_path,
            poll_interval=8.0,
            watcher_markets="BTC,ETH,INJ",
            sentinel_host="0.0.0.0",
            sentinel_port=8000,
            sentinel_env="development",
            sentinel_api_key="",
            require_api_key=False,
            cors_origins="http://localhost:3000",
            enable_docs=True,
            runtime_api_url="http://127.0.0.1:8000",
        )

        proposal = Proposal(
            id="p1",
            event_id="e1",
            ts=datetime.now(timezone.utc),
            action="open",
            market="BTC",
            side="short",
            notional_usd=10.0,
            leverage=2.0,
            reasoning="test",
            confidence=0.9,
            expected_hold_hours=1.0,
            invalidation="x",
        )
        await self.store.save_proposal(proposal)

        verdict = RiskVerdict(
            proposal_id="p1",
            ts=datetime.now(timezone.utc),
            approved=True,
            reasons=["ok"],
            modified_notional=10.0,
            modified_leverage=2.0,
        )
        await self.store.save_verdict(verdict)

        fake = _FakeMCP()
        with patch("sentinel.agents.executor.get_mcp_client", AsyncMock(return_value=fake)):
            await ex._process_verdict(
                bus=self.bus,
                store=self.store,
                config=config,
                verdict_msg={**verdict.model_dump(mode="json"), "proposal": proposal.model_dump(mode="json")},
            )

        # Only transfer_send should be called (not trade_open)
        tools = [c[0] for c in fake.calls]
        self.assertIn("transfer_send", tools)
        self.assertNotIn("trade_open", tools)

        execution = await self.store.get_execution_for_proposal("p1")
        assert execution is not None
        self.assertEqual(execution["status"], "success")
        self.assertEqual(execution["tool_called"], "transfer_send")
        self.assertEqual(execution["tx_hash"], "ABC123REALTXHASH")
        self.assertFalse(str(execution["tx_hash"]).startswith("dry-run-"))

    async def test_demo_disabled_keeps_dry_run_trade_open_path(self) -> None:
        from sentinel.agents import executor as ex
        from sentinel.config import Settings

        config = Settings.model_construct(
            anthropic_api_key="x",
            groq_api_key="x",
            simulator_mode=True,
            dry_run=True,
            demo_real_tx=False,
            demo_tx_amount="0.1",
            demo_tx_recipient="",
            injective_network="testnet",
            injective_wallet_address="inj1h07rx97gmplmsthnqt3r4ntte95vy96mxpvhnp",
            injective_wallet_password="pw",
            mcp_server_path="",
            sentinel_db_path=self.db_path,
            poll_interval=8.0,
            watcher_markets="BTC,ETH,INJ",
            sentinel_host="0.0.0.0",
            sentinel_port=8000,
            sentinel_env="development",
            sentinel_api_key="",
            require_api_key=False,
            cors_origins="http://localhost:3000",
            enable_docs=True,
            runtime_api_url="http://127.0.0.1:8000",
        )

        proposal = Proposal(
            id="p2",
            event_id="e2",
            ts=datetime.now(timezone.utc),
            action="open",
            market="BTC",
            side="long",
            notional_usd=50.0,
            leverage=2.0,
            reasoning="test",
            confidence=0.9,
            expected_hold_hours=1.0,
            invalidation="x",
        )
        await self.store.save_proposal(proposal)

        verdict = RiskVerdict(
            proposal_id="p2",
            ts=datetime.now(timezone.utc),
            approved=True,
            reasons=["ok"],
            modified_notional=50.0,
            modified_leverage=2.0,
        )
        await self.store.save_verdict(verdict)

        # In dry-run open path, executor doesn't need an MCP client.
        await ex._process_verdict(
            bus=self.bus,
            store=self.store,
            config=config,
            verdict_msg={**verdict.model_dump(mode="json"), "proposal": proposal.model_dump(mode="json")},
        )

        execution = await self.store.get_execution_for_proposal("p2")
        assert execution is not None
        self.assertEqual(execution["status"], "success")
        self.assertEqual(execution["tool_called"], "trade_open")
        self.assertTrue(str(execution["tx_hash"]).startswith("dry-run-"))


if __name__ == "__main__":
    unittest.main()

