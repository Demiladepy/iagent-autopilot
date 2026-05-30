"""Runtime API hardening: config, probes, WebSocket hub, CORS, errors."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.websockets import WebSocketDisconnect, WebSocketState

from sentinel.config import (
    Settings,
    collect_config_issues,
    validate_settings_or_exit,
)
from sentinel.errors import error_body
from sentinel.websocket_hub import WebSocketHub
from tests.base import SentinelClientTestCase


def _minimal_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "anthropic_api_key": "test-anthropic",
        "groq_api_key": "test-groq",
        "simulator_mode": True,
        "dry_run": True,
        "mcp_server_path": "",
        "cors_origins": "http://localhost:3000",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


class ConfigValidationTests(unittest.TestCase):
    def test_missing_anthropic_key_reported(self) -> None:
        issues = collect_config_issues(_minimal_settings(anthropic_api_key=""))
        self.assertTrue(any("ANTHROPIC_API_KEY" in i for i in issues))

    def test_missing_mcp_path_when_live_mode(self) -> None:
        issues = collect_config_issues(
            _minimal_settings(simulator_mode=False, mcp_server_path="")
        )
        self.assertTrue(any("MCP_SERVER_PATH" in i for i in issues))

    def test_mcp_path_must_exist_on_disk(self) -> None:
        issues = collect_config_issues(
            _minimal_settings(
                simulator_mode=False,
                mcp_server_path="/nonexistent/mcp/server.js",
            )
        )
        self.assertTrue(any("does not exist on disk" in i for i in issues))

    def test_cors_wildcard_rejected_with_api_key(self) -> None:
        issues = collect_config_issues(
            _minimal_settings(
                sentinel_api_key="secret",
                require_api_key=True,
                cors_origins="*",
            )
        )
        self.assertTrue(any("cannot include '*'" in i for i in issues))

    def test_validate_or_exit_prints_checklist(self) -> None:
        with patch("sys.stderr") as stderr:
            with self.assertRaises(SystemExit) as ctx:
                validate_settings_or_exit(_minimal_settings(anthropic_api_key=""))
        self.assertEqual(ctx.exception.code, 1)
        err_text = "".join(str(c[0][0]) for c in stderr.write.call_args_list)
        self.assertIn("ANTHROPIC_API_KEY", err_text)


class ReadyProbeTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SIMULATOR_MODE"] = "true"
        os.environ["SENTINEL_API_KEY"] = ""
        os.environ["REQUIRE_API_KEY"] = "false"
        super().setUpClass()

    def test_health_always_ok_while_starting_flag_irrelevant(self) -> None:
        import sentinel.main as main

        main.state.lifecycle_ready = False
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

    @patch("sentinel.main.mcp_client_is_healthy", return_value=False)
    def test_ready_503_when_mcp_marked_unhealthy(self, _mock: MagicMock) -> None:
        import sentinel.main as main

        with tempfile.NamedTemporaryFile(suffix=".mjs", delete=False) as tmp:
            tmp.write(b"// fake mcp path for readiness probe")
            mcp_path = tmp.name

        main.state.settings = main.state.settings.model_copy(
            update={
                "simulator_mode": False,
                "dry_run": False,
                "mcp_server_path": mcp_path,
            }
        )
        main.state.mcp_connected = True
        self.assertFalse(main.state.settings.simulator_mode)
        self.assertFalse(main.state.settings.dry_run)

        res = self.client.get("/ready")
        self.assertEqual(res.status_code, 503)
        body = res.json()
        self.assertEqual(body["error"]["code"], "not_ready")
        checks = body["error"]["details"]
        mcp_check = next(c for c in checks if c["name"] == "mcp")
        self.assertFalse(mcp_check["ok"])
        self.assertIn("unhealthy", mcp_check["detail"].lower())


class AuthAndCorsTests(SentinelClientTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SENTINEL_API_KEY"] = "test-secret-key"
        os.environ["REQUIRE_API_KEY"] = "true"
        os.environ["CORS_ORIGINS"] = "http://localhost:3000"
        os.environ["SIMULATOR_MODE"] = "true"
        super().setUpClass()

    def test_protected_401_without_key(self) -> None:
        res = self.client.get("/state")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"]["code"], "unauthorized")

    def test_protected_200_with_key(self) -> None:
        res = self.client.get("/state", headers={"X-Sentinel-API-Key": "test-secret-key"})
        self.assertEqual(res.status_code, 200)

    def test_health_and_ready_public(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)

    def test_cors_allows_configured_origin(self) -> None:
        res = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(
            res.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )
        self.assertNotEqual(res.headers.get("access-control-allow-origin"), "*")

    def test_ws_rejects_without_key(self) -> None:
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws"):
                pass


class WebSocketHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_drops_dead_client(self) -> None:
        hub = WebSocketHub()
        live = MagicMock()
        live.client_state = WebSocketState.CONNECTED
        live.send_json = AsyncMock()

        dead = MagicMock()
        dead.client_state = WebSocketState.CONNECTED
        dead.send_json = AsyncMock(side_effect=ConnectionError("gone"))

        await hub.register(live)
        await hub.register(dead)
        await hub.broadcast({"topic": "test", "n": 1})

        live.send_json.assert_awaited_once()
        self.assertEqual(hub.client_count, 1)

    async def test_unregister_on_disconnect(self) -> None:
        hub = WebSocketHub()
        ws = MagicMock()
        await hub.register(ws)
        await hub.unregister(ws)
        self.assertEqual(hub.client_count, 0)


class ErrorEnvelopeTests(SentinelClientTestCase):
    def test_error_body_shape(self) -> None:
        body = error_body(code="test", message="hello", request_id="req-1")
        self.assertEqual(body["error"]["code"], "test")
        self.assertEqual(body["request_id"], "req-1")


if __name__ == "__main__":
    unittest.main()
