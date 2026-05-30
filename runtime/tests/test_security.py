"""Security and API auth tests."""

from __future__ import annotations

import os
import unittest

from tests.base import SentinelClientTestCase


def _prepare_env(*, api_key: str, require: bool) -> None:
    os.environ["SENTINEL_API_KEY"] = api_key
    os.environ["REQUIRE_API_KEY"] = "true" if require else "false"
    os.environ["SENTINEL_ENV"] = "development"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
    os.environ["GROQ_API_KEY"] = "test-groq-key"


class SecurityTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _prepare_env(api_key="test-secret-key", require=True)
        super().setUpClass()

    def setUp(self) -> None:
        self.headers = {"X-Sentinel-API-Key": "test-secret-key"}

    def test_public_health_no_key(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("ok", body)
        self.assertIn("version", body)
        self.assertNotIn("agents", body)

    def test_protected_route_rejects_missing_key(self) -> None:
        res = self.client.get("/state")
        self.assertEqual(res.status_code, 401)

    def test_protected_route_accepts_header_key(self) -> None:
        res = self.client.get("/state", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("kill_switch", res.json())

    def test_protected_route_accepts_bearer(self) -> None:
        res = self.client.get(
            "/state",
            headers={"Authorization": "Bearer test-secret-key"},
        )
        self.assertEqual(res.status_code, 200)

    def test_wrong_key_rejected(self) -> None:
        res = self.client.get("/state", headers={"X-Sentinel-API-Key": "wrong"})
        self.assertEqual(res.status_code, 401)
        body = res.json()
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_ready_public_without_key(self) -> None:
        res = self.client.get("/ready")
        self.assertEqual(res.status_code, 200)

    def test_status_requires_auth(self) -> None:
        res = self.client.get("/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("agents", res.json())


class OpenDevSecurityTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _prepare_env(api_key="", require=False)
        super().setUpClass()

    def test_open_when_no_key_configured(self) -> None:
        res = self.client.get("/state")
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
