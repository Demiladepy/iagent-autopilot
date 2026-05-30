"""HTTP API smoke tests (open dev mode)."""

from __future__ import annotations

import os
import unittest

from tests.base import SentinelClientTestCase


class ApiSmokeTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SENTINEL_API_KEY"] = ""
        os.environ["REQUIRE_API_KEY"] = "false"
        os.environ["SIMULATOR_MODE"] = "true"
        os.environ["SENTINEL_ENV"] = "development"
        super().setUpClass()

    def test_health_and_ready(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["ok"])
        ready = self.client.get("/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["ok"])

    def test_state_and_strategy(self) -> None:
        state_res = self.client.get("/state")
        self.assertEqual(state_res.status_code, 200)
        strat = self.client.get("/strategy")
        self.assertEqual(strat.status_code, 200)


if __name__ == "__main__":
    unittest.main()
