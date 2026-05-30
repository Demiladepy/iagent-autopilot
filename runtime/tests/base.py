"""Shared test helpers."""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from sentinel.config import get_settings


class SentinelClientTestCase(unittest.TestCase):
    """TestCase that runs FastAPI lifespan (DB connect, agents)."""

    client: TestClient
    _client_ctx: TestClient

    @classmethod
    def make_client(cls, *, reload_main: bool = True) -> TestClient:
        get_settings.cache_clear()
        if reload_main:
            import sentinel.main as main

            main.state = main._build_app_state()
            return TestClient(main.create_app())
        from sentinel.main import create_app

        return TestClient(create_app())

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SENTINEL_DB_PATH"] = tempfile.mktemp(suffix="-sentinel-test.db")
        os.environ["DRY_RUN"] = "true"
        os.environ["MCP_SERVER_PATH"] = ""
        os.environ["SIMULATOR_MODE"] = "true"
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
        os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
        os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
        cls._client_ctx = cls.make_client()
        cls.client = cls._client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_ctx.__exit__(None, None, None)
