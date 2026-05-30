"""Agent hardening: resilience, validation, executor gates, risk determinism."""

from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from sentinel.agents import analyst, auditor, executor, risk, watcher
from sentinel.bus import TOPIC_EVENT, TOPIC_EXECUTION, TOPIC_PROPOSAL, TOPIC_VERDICT, EventBus
from sentinel.config import Settings
from sentinel.llm.anthropic_client import AnthropicCallResult
from sentinel.mcp_client import MCP_WRITE_TOOLS
from sentinel.schemas import Proposal, ProposalOutput
from sentinel.store import SentinelStore


def _settings(**overrides: Any) -> Settings:
    base = {
        "anthropic_api_key": "test",
        "groq_api_key": "test",
        "mcp_server_path": "",
        "dry_run": False,
        "simulator_mode": True,
        "kill_switch": False,
        "injective_wallet_address": "inj1test",
        "injective_wallet_password": "secret",
    }
    base.update(overrides)
    return Settings(**base)


def _event_msg(event_id: str, market: str = "BTC") -> dict[str, Any]:
    return {
        "id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "synthetic",
        "market": market,
        "payload": {"note": "test"},
        "source": "simulator",
    }


def _proposal_msg(
    proposal_id: str,
    event_id: str,
    *,
    action: str = "open",
    notional: float = 25.0,
    market: str = "BTC",
) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "market": market,
        "side": "long",
        "notional_usd": notional,
        "leverage": 2.0,
        "reasoning": "test proposal",
        "confidence": 0.8,
        "expected_hold_hours": 4.0,
        "invalidation": "price reverses 2%",
    }


async def _proposal_for_event(store: SentinelStore, event_id: str) -> dict[str, Any] | None:
    assert store._db is not None
    async with store._db.execute(
        "SELECT * FROM proposals WHERE event_id = ? ORDER BY ts DESC LIMIT 1",
        (event_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def _run_agent_briefly(coro) -> None:
    task = asyncio.create_task(coro)
    await asyncio.sleep(0.6)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class AgentResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = tempfile.mktemp(suffix="-agents-test.db")
        self.store = SentinelStore(self.db_path)
        await self.store.connect()
        self.bus = EventBus()
        self.config = _settings()

    async def asyncTearDown(self) -> None:
        await self.store.close()

    async def test_analyst_survives_poison_then_processes_next(self) -> None:
        calls = {"n": 0}

        async def flaky_strategy() -> dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("poisoned strategy read")
            return {
                "text": "test",
                "max_notional_usd": 50.0,
                "max_leverage": 2.0,
                "max_daily_loss_usd": 25.0,
                "allowed_markets": ["BTC"],
            }

        valid = ProposalOutput(
            action="open",
            market="BTC",
            side="long",
            notional_usd=25.0,
            leverage=2.0,
            reasoning="valid",
            confidence=0.7,
            expected_hold_hours=2.0,
            invalidation="if price dumps",
        )

        with (
            patch.object(self.store, "get_strategy", flaky_strategy),
            patch(
                "sentinel.agents.analyst.anthropic_client.generate_proposal",
                new=AsyncMock(
                    return_value=AnthropicCallResult(
                        parsed=valid,
                        latency_ms=1.0,
                        input_tokens=1,
                        output_tokens=1,
                        raw_text="{}",
                    )
                ),
            ),
        ):
            task = asyncio.create_task(
                analyst.run(bus=self.bus, store=self.store, config=self.config)
            )
            await asyncio.sleep(0.2)
            await self.bus.publish(TOPIC_EVENT, _event_msg("evt-poison"))
            await self.bus.publish(TOPIC_EVENT, _event_msg("evt-ok"))
            await asyncio.sleep(0.8)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.assertTrue(await self.store.has_proposal_for_event("evt-ok"))
        row = await _proposal_for_event(self.store, "evt-ok")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["action"], "open")

    async def test_risk_survives_poison_then_processes_next(self) -> None:
        calls = {"n": 0}

        async def flaky_pnl() -> float:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("poison pnl")
            return 0.0

        with patch.object(self.store, "today_pnl", flaky_pnl):
            task = asyncio.create_task(
                risk.run(bus=self.bus, store=self.store, config=self.config)
            )
            await asyncio.sleep(0.2)
            await self.bus.publish(TOPIC_PROPOSAL, _proposal_msg("p-poison", "e1"))
            await self.bus.publish(
                TOPIC_PROPOSAL, _proposal_msg("p-ok", "e2", action="none")
            )
            await asyncio.sleep(0.8)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        verdict = await self.store.get_verdict("p-ok")
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertTrue(verdict["approved"])

    async def test_executor_survives_poison_then_processes_next(self) -> None:
        calls = {"n": 0}

        async def flaky_get_proposal(pid: str) -> dict[str, Any] | None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("poison proposal load")
            return _proposal_msg("p-ok", "e2", action="none")

        config = _settings(dry_run=True)
        with patch.object(self.store, "get_proposal", flaky_get_proposal):
            task = asyncio.create_task(
                executor.run(bus=self.bus, store=self.store, config=config)
            )
            await asyncio.sleep(0.2)
            await self.bus.publish(
                TOPIC_VERDICT,
                {
                    "proposal_id": "p-poison",
                    "approved": True,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "reasons": [],
                },
            )
            await self.bus.publish(
                TOPIC_VERDICT,
                {
                    "proposal_id": "p-ok",
                    "approved": True,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "reasons": [],
                    "modified_notional": None,
                },
            )
            await asyncio.sleep(0.8)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        ex = await self.store.get_execution_for_proposal("p-ok")
        self.assertIsNotNone(ex)
        assert ex is not None
        self.assertEqual(ex["status"], "skipped")

    async def test_auditor_survives_poison_then_processes_next(self) -> None:
        calls = {"n": 0}

        async def flaky_explain(*_a: Any, **_k: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("poison audit")
            result = MagicMock()
            result.summary = "ok summary"
            result.flags = []
            return result

        with patch(
            "sentinel.agents.auditor.anthropic_client.explain_execution",
            flaky_explain,
        ):
            task = asyncio.create_task(
                auditor.run(bus=self.bus, store=self.store, config=self.config)
            )
            await asyncio.sleep(0.2)
            await self.bus.publish(
                TOPIC_EXECUTION,
                {"id": "ex-poison", "proposal_id": "p1", "status": "skipped"},
            )
            await self.bus.publish(
                TOPIC_EXECUTION,
                {"id": "ex-ok", "proposal_id": "p2", "status": "skipped"},
            )
            await asyncio.sleep(0.8)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        note = await self.store.get_audit_for_execution("ex-ok")
        self.assertIsNotNone(note)

    async def test_watcher_survives_poison_then_processes_next(self) -> None:
        config = _settings(simulator_mode=True)
        calls = {"n": 0}
        real_emit = watcher.Watcher._emit

        async def flaky_emit(self_w: watcher.Watcher, event, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("poison emit")
            await real_emit(self_w, event, **kwargs)

        from sentinel.bus import TOPIC_SIM_INJECT

        with patch.object(watcher.Watcher, "_emit", flaky_emit):
            w = watcher.Watcher(
                bus=self.bus,
                store=self.store,
                config=config,
                kill_event=asyncio.Event(),
            )
            task = asyncio.create_task(w.run())
            await asyncio.sleep(0.3)
            await self.bus.publish(TOPIC_SIM_INJECT, _event_msg("w-poison"))
            await self.bus.publish(TOPIC_SIM_INJECT, _event_msg("w-ok"))
            await asyncio.sleep(0.8)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.assertGreaterEqual(calls["n"], 2)


class AnalystValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_garbage_llm_then_valid(self) -> None:
        db_path = tempfile.mktemp(suffix="-analyst-val.db")
        store = SentinelStore(db_path)
        await store.connect()
        bus = EventBus()
        config = _settings()

        invalid = ProposalOutput.model_construct(
            action="open",
            market="BTC",
            side="long",
            notional_usd=100.0,
            leverage=2.0,
            reasoning="bad",
            confidence=1.5,
            expected_hold_hours=1.0,
            invalidation=None,
        )
        valid = ProposalOutput(
            action="open",
            market="BTC",
            side="long",
            notional_usd=25.0,
            leverage=2.0,
            reasoning="good",
            confidence=0.7,
            expected_hold_hours=2.0,
            invalidation="if dump",
        )

        def _result(parsed: ProposalOutput) -> AnthropicCallResult:
            return AnthropicCallResult(
                parsed=parsed,
                latency_ms=1.0,
                input_tokens=1,
                output_tokens=1,
                raw_text="{}",
            )

        mock_gen = AsyncMock(
            side_effect=[
                _result(invalid),
                _result(invalid),
                _result(valid),
            ]
        )

        with patch("sentinel.agents.analyst.anthropic_client.generate_proposal", mock_gen):
            task = asyncio.create_task(analyst.run(bus=bus, store=store, config=config))
            await asyncio.sleep(0.3)
            await bus.publish(TOPIC_EVENT, _event_msg("e-garbage"))
            await bus.publish(TOPIC_EVENT, _event_msg("e-valid"))
            await asyncio.sleep(0.8)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        row_bad = await _proposal_for_event(store, "e-garbage")
        row_ok = await _proposal_for_event(store, "e-valid")
        self.assertIsNotNone(row_bad)
        self.assertIsNotNone(row_ok)
        assert row_bad is not None and row_ok is not None
        self.assertEqual(row_bad["action"], "none")
        self.assertEqual(row_ok["action"], "open")
        await store.close()


class ExecutorGateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = tempfile.mktemp(suffix="-executor-test.db")
        self.store = SentinelStore(self.db_path)
        await self.store.connect()
        self.bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.store.close()

    async def _save_proposal(self, msg: dict[str, Any]) -> None:
        await self.store.save_proposal(
            Proposal(
                id=msg["id"],
                event_id=msg["event_id"],
                ts=datetime.fromisoformat(msg["ts"].replace("Z", "+00:00")),
                action=msg["action"],
                market=msg.get("market"),
                side=msg.get("side"),
                notional_usd=msg.get("notional_usd"),
                leverage=msg.get("leverage"),
                reasoning=msg["reasoning"],
                confidence=msg["confidence"],
                expected_hold_hours=msg.get("expected_hold_hours"),
                invalidation=msg.get("invalidation"),
            )
        )

    async def test_dry_run_does_not_call_write_tools(self) -> None:
        config = _settings(dry_run=True)
        prop = _proposal_msg("prop-dry", "e1")
        await self._save_proposal(prop)
        mock_mcp = MagicMock()
        mock_mcp.is_healthy.return_value = True
        mock_mcp.call = AsyncMock(return_value=[{"symbol": "BTC", "ticker": "BTC/USDT PERP"}])

        with patch("sentinel.agents.executor.get_mcp_client", AsyncMock(return_value=mock_mcp)):
            await executor._process_verdict(
                bus=self.bus,
                store=self.store,
                config=config,
                verdict_msg={
                    "proposal_id": "prop-dry",
                    "approved": True,
                    "modified_notional": 25.0,
                    "modified_leverage": 2.0,
                },
            )

        write_calls = [
            c for c in mock_mcp.call.call_args_list if c.args[0] in MCP_WRITE_TOOLS
        ]
        self.assertEqual(write_calls, [])
        ex = await self.store.get_execution_for_proposal("prop-dry")
        self.assertIsNotNone(ex)
        assert ex is not None
        self.assertEqual(ex["status"], "success")
        self.assertTrue(str(ex["tx_hash"]).startswith("dry-run-"))

    async def test_live_mode_calls_mcp_write(self) -> None:
        config = _settings(dry_run=False)
        await self._save_proposal(_proposal_msg("prop-live", "e1"))
        mock_mcp = MagicMock()
        mock_mcp.is_healthy.return_value = True
        mock_mcp.call = AsyncMock(
            side_effect=[
                [{"symbol": "BTC", "ticker": "BTC/USDT PERP"}],
                {"txHash": "0xabc"},
            ]
        )

        with patch("sentinel.agents.executor.get_mcp_client", AsyncMock(return_value=mock_mcp)):
            await executor._process_verdict(
                bus=self.bus,
                store=self.store,
                config=config,
                verdict_msg={
                    "proposal_id": "prop-live",
                    "approved": True,
                    "modified_notional": 25.0,
                    "modified_leverage": 2.0,
                },
            )

        tools = [c.args[0] for c in mock_mcp.call.call_args_list]
        self.assertIn("trade_open", tools)
        ex = await self.store.get_execution_for_proposal("prop-live")
        self.assertIsNotNone(ex)
        assert ex is not None
        self.assertEqual(ex["status"], "success")

    async def test_idempotency_skips_second_execution(self) -> None:
        config = _settings(dry_run=True)
        await self._save_proposal(_proposal_msg("prop-idem", "e1"))
        verdict = {
            "proposal_id": "prop-idem",
            "approved": True,
            "modified_notional": 10.0,
        }
        await executor._process_verdict(
            bus=self.bus, store=self.store, config=config, verdict_msg=verdict
        )
        await executor._process_verdict(
            bus=self.bus, store=self.store, config=config, verdict_msg=verdict
        )

        assert self.store._db is not None
        async with self.store._db.execute(
            "SELECT COUNT(*) AS c FROM executions WHERE proposal_id = ? AND status = 'success'",
            ("prop-idem",),
        ) as cur:
            row = await cur.fetchone()
        self.assertEqual(row["c"], 1)


class WriteToolIsolationTests(unittest.TestCase):
    def test_only_executor_references_write_tools(self) -> None:
        read_only_modules = [analyst, risk, watcher, auditor]
        for mod in read_only_modules:
            source = inspect.getsource(mod)
            for tool in MCP_WRITE_TOOLS:
                self.assertNotIn(
                    f'call("{tool}"',
                    source,
                    f"{mod.__name__} must not call write tool {tool}",
                )
                self.assertNotIn(
                    f"call('{tool}'",
                    source,
                    f"{mod.__name__} must not call write tool {tool}",
                )


class RiskDeterminismTests(unittest.IsolatedAsyncioTestCase):
    async def test_notional_clamped_despite_groq_approve(self) -> None:
        strategy = {
            "max_notional_usd": 50.0,
            "max_leverage": 5.0,
            "max_daily_loss_usd": 500.0,
            "allowed_markets": ["BTC"],
        }
        proposal = _proposal_msg("p-cap", "e1", notional=500.0)
        det = risk._run_deterministic_checks(
            proposal,
            strategy=strategy,
            today_pnl=0.0,
            positions=[],
            kill_switch=False,
        )
        self.assertTrue(det.approved)
        self.assertFalse(det.hard_reject)
        self.assertEqual(det.modified_notional, 50.0)

        approved = det.approved
        with patch(
            "sentinel.agents.risk.groq_client.risk_sanity_check",
            AsyncMock(return_value=(True, "groq_approve", 1.0)),
        ):
            if approved and not det.hard_reject and proposal.get("action") != "none":
                groq_ok, _, _ = await risk.groq_client.risk_sanity_check(
                    _settings(), "", ""
                )
                if not groq_ok:
                    approved = False
        self.assertTrue(approved)
        self.assertEqual(det.modified_notional, 50.0)

    async def test_hard_reject_not_overturned_by_groq(self) -> None:
        strategy = {
            "max_notional_usd": 50.0,
            "max_leverage": 5.0,
            "max_daily_loss_usd": 500.0,
            "allowed_markets": ["BTC"],
        }
        proposal = _proposal_msg("p-rej", "e1", market="DOGE")
        det = risk._run_deterministic_checks(
            proposal,
            strategy=strategy,
            today_pnl=0.0,
            positions=[],
            kill_switch=False,
        )
        self.assertFalse(det.approved)
        self.assertTrue(det.hard_reject)

        with patch(
            "sentinel.agents.risk.groq_client.risk_sanity_check",
            AsyncMock(return_value=(True, "groq_approve", 1.0)),
        ):
            approved = det.approved
            if approved and not det.hard_reject and proposal.get("action") != "none":
                groq_ok, _, _ = await risk.groq_client.risk_sanity_check(
                    _settings(), "", ""
                )
                if not groq_ok:
                    approved = False
        self.assertFalse(approved)

    async def test_kill_switch_rejects_open(self) -> None:
        db_path = tempfile.mktemp(suffix="-risk-kill.db")
        store = SentinelStore(db_path)
        await store.connect()
        store.kill_switch_active = True
        bus = EventBus()
        config = _settings(kill_switch=False)

        task = asyncio.create_task(risk.run(bus=bus, store=store, config=config))
        await asyncio.sleep(0.2)
        await bus.publish(TOPIC_PROPOSAL, _proposal_msg("p-kill", "e1", action="open"))
        await asyncio.sleep(0.6)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        verdict = await store.get_verdict("p-kill")
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertFalse(verdict["approved"])
        self.assertIn("kill_switch_active", verdict["reasons"])
        await store.close()


if __name__ == "__main__":
    unittest.main()
