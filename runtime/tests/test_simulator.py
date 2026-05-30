"""Tests for sentinel.simulator."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from sentinel.bus import TOPIC_EVENT, EventBus
from sentinel.schemas import MarketEvent
from sentinel.simulator import (
    SCENARIOS,
    inject_custom_event,
    inject_event,
    list_scenarios,
    start_scenario,
)


class InMemoryStore:
    """Minimal store stub for simulator tests."""

    def __init__(self) -> None:
        self.events: list[MarketEvent] = []

    async def save_event(self, event: MarketEvent) -> None:
        self.events.append(event)


class SimulatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_scenarios(self) -> None:
        names = {s["name"] for s in list_scenarios()}
        self.assertEqual(names, set(SCENARIOS.keys()))

    async def test_inject_event_publishes_on_event_topic(self) -> None:
        bus = EventBus()
        store = InMemoryStore()
        received: list[dict] = []

        async def collector() -> None:
            async for msg in bus.subscribe(TOPIC_EVENT):
                received.append(msg)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.05)

        event = MarketEvent(
            id="test-event-1",
            ts=datetime.now(timezone.utc),
            kind="breakout",
            market="BTC",
            payload={"rationale": "unit test"},
            source="simulator",
        )
        await inject_event(bus, store, event)
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        self.assertEqual(len(store.events), 1)
        self.assertEqual(store.events[0].source, "simulator")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["topic"], TOPIC_EVENT)
        self.assertEqual(received[0]["kind"], "breakout")
        self.assertEqual(received[0]["market"], "BTC")

    async def test_funding_reversion_scenario_timing(self) -> None:
        bus = EventBus()
        store = InMemoryStore()
        received: list[dict] = []

        async def collector() -> None:
            async for msg in bus.subscribe(TOPIC_EVENT):
                received.append(msg)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.02)

        # Use a compressed test scenario inline
        from sentinel import simulator as sim_mod

        original = sim_mod.SCENARIOS["funding_reversion"]
        sim_mod.SCENARIOS["funding_reversion"] = [
            (0, "funding_flip", "BTC", {"rationale": "t0"}),
            (1, "drawdown", "ETH", {"rationale": "t1"}),
            (2, "breakout", "INJ", {"rationale": "t2"}),
        ]
        try:
            result = await start_scenario(
                bus, store, "funding_reversion", wait=True
            )
        finally:
            sim_mod.SCENARIOS["funding_reversion"] = original

        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["event_ids"]), 3)
        self.assertEqual(len(store.events), 3)
        self.assertEqual(len(received), 3)
        self.assertTrue(all(m.get("source") == "simulator" for m in received))
        kinds = [m["kind"] for m in received]
        self.assertEqual(kinds, ["funding_flip", "drawdown", "breakout"])

    async def test_unknown_scenario_raises(self) -> None:
        bus = EventBus()
        store = InMemoryStore()
        with self.assertRaises(ValueError):
            await start_scenario(bus, store, "nonexistent", wait=True)

    async def test_inject_custom_event(self) -> None:
        bus = EventBus()
        store = InMemoryStore()
        event = await inject_custom_event(
            bus,
            store,
            kind="manual",
            market="INJ",
            payload={"rationale": "custom shot"},
        )
        self.assertEqual(event.kind, "manual")
        self.assertEqual(event.market, "INJ")
        self.assertEqual(len(store.events), 1)


if __name__ == "__main__":
    unittest.main()
