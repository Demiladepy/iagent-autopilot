from __future__ import annotations

import os
import sys
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigValidationError(RuntimeError):
    """Startup configuration failed — see .issues for a checklist."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        message = "Configuration validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
        super().__init__(message)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    groq_api_key: str = ""
    injective_network: str = "testnet"
    injective_wallet_address: str = ""
    injective_wallet_password: str = ""
    mcp_server_path: str = ""
    mcp_handshake_timeout: float = Field(
        default=15.0,
        validation_alias="MCP_HANDSHAKE_TIMEOUT",
    )
    mcp_tool_call_timeout: float = Field(
        default=30.0,
        validation_alias="MCP_TOOL_CALL_TIMEOUT",
    )
    mcp_request_timeout: float = Field(
        default=120.0,
        validation_alias="MCP_REQUEST_TIMEOUT",
    )
    simulator_mode: bool = True
    dry_run: bool = False
    demo_real_tx: bool = Field(default=False, validation_alias="DEMO_REAL_TX")
    demo_tx_amount: str = Field(default="0.1", validation_alias="DEMO_TX_AMOUNT")
    demo_tx_recipient: str = Field(default="", validation_alias="DEMO_TX_RECIPIENT")
    sentinel_db_path: str = "./sentinel.db"
    kill_switch: bool = False
    poll_interval: float = 8.0
    watcher_markets: str = "BTC,ETH,INJ"
    sentinel_host: str = "0.0.0.0"
    sentinel_port: int = Field(default=8000, validation_alias="PORT")

    # Security / production
    sentinel_env: str = Field(default="development", validation_alias="SENTINEL_ENV")
    sentinel_api_key: str = Field(default="", validation_alias="SENTINEL_API_KEY")
    require_api_key: bool = Field(default=False, validation_alias="REQUIRE_API_KEY")
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )
    enable_docs: bool | None = Field(default=None, validation_alias="ENABLE_DOCS")

    runtime_api_url: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias="RUNTIME_API_URL",
    )

    @field_validator("sentinel_api_key", mode="before")
    @classmethod
    def _strip_api_key(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("mcp_handshake_timeout", "mcp_tool_call_timeout", "mcp_request_timeout")
    @classmethod
    def _positive_timeout(cls, v: object) -> float:
        value = float(v)
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @property
    def is_production(self) -> bool:
        return self.sentinel_env.lower() in ("production", "prod")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return not self.is_production

    @property
    def auth_enabled(self) -> bool:
        return self.require_api_key or bool(self.sentinel_api_key)


def auth_required(settings: Settings) -> bool:
    return settings.auth_enabled


def collect_config_issues(settings: Settings) -> list[str]:
    """Return human-readable configuration problems (empty if OK)."""
    issues: list[str] = []

    if not settings.anthropic_api_key.strip():
        issues.append(
            "ANTHROPIC_API_KEY is not set — required for Analyst, Auditor, and strategy parse"
        )
    if not settings.groq_api_key.strip():
        issues.append("GROQ_API_KEY is not set — required for Watcher and Risk agents")

    if settings.mcp_handshake_timeout <= 0:
        issues.append("MCP_HANDSHAKE_TIMEOUT must be a positive number")
    if settings.mcp_tool_call_timeout <= 0:
        issues.append("MCP_TOOL_CALL_TIMEOUT must be a positive number")

    if not settings.simulator_mode:
        if not settings.mcp_server_path.strip():
            issues.append(
                "MCP_SERVER_PATH is not set — required when SIMULATOR_MODE=false "
                "(path to mcp-server/dist/mcp/server.js)"
            )
        else:
            path = os.path.abspath(settings.mcp_server_path)
            if not os.path.isfile(path):
                issues.append(f"MCP_SERVER_PATH does not exist on disk: {path}")

        if settings.mcp_server_path.strip() and not settings.dry_run:
            if not settings.injective_wallet_address.strip():
                issues.append(
                    "INJECTIVE_WALLET_ADDRESS is not set — required for live MCP trading"
                )
            if not settings.injective_wallet_password.strip():
                issues.append(
                    "INJECTIVE_WALLET_PASSWORD is not set — required for live MCP trading"
                )

    if settings.auth_enabled:
        if not settings.sentinel_api_key:
            issues.append(
                "SENTINEL_API_KEY must be set when REQUIRE_API_KEY=true or when using API auth"
            )
        origins = settings.cors_origin_list
        if not origins:
            issues.append(
                "CORS_ORIGINS must list allowed dashboard origin(s) when API key auth is enabled"
            )
        if "*" in origins:
            issues.append(
                "CORS_ORIGINS cannot include '*' when SENTINEL_API_KEY is set — use explicit origins"
            )

    if settings.is_production and settings.auth_enabled and not settings.sentinel_api_key:
        issues.append("Production requires SENTINEL_API_KEY when API authentication is enabled")

    if settings.poll_interval <= 0:
        issues.append("POLL_INTERVAL must be positive")

    return issues


def validate_settings(settings: Settings) -> None:
    """Raise ConfigValidationError with a printable checklist if invalid."""
    issues = collect_config_issues(settings)
    if issues:
        raise ConfigValidationError(issues)


def validate_settings_or_exit(settings: Settings | None = None) -> Settings:
    """Validate env config and exit with checklist on failure (for startup)."""
    settings = settings or get_settings()
    issues = collect_config_issues(settings)
    if issues:
        print("iAgent Autopilot — configuration checklist (fix before starting):\n", file=sys.stderr)
        for item in issues:
            print(f"  [ ] {item}", file=sys.stderr)
        print(file=sys.stderr)
        raise SystemExit(1)
    return settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
