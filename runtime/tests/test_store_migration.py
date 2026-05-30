"""Regression: schema migration self-heals old DBs (no column crashes)."""

from __future__ import annotations

import tempfile
import unittest

import aiosqlite

from sentinel.store import SentinelStore


class StoreMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_strategy_table_upgrades_missing_text_column(self) -> None:
        db_path = tempfile.mktemp(suffix="-old-schema.db")

        # Create an old schema: strategy table without `text`.
        db = await aiosqlite.connect(db_path)
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS strategy (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    max_notional_usd REAL NOT NULL DEFAULT 1000,
                    max_leverage REAL NOT NULL DEFAULT 10,
                    max_daily_loss_usd REAL NOT NULL DEFAULT 500,
                    allowed_markets TEXT NOT NULL DEFAULT '["BTC","ETH","INJ"]',
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO strategy (
                    id, max_notional_usd, max_leverage, max_daily_loss_usd, allowed_markets, updated_at
                ) VALUES (1, 1000, 10, 500, '["BTC","ETH","INJ"]', '2026-01-01T00:00:00+00:00');
                """
            )
            await db.commit()
        finally:
            await db.close()

        store = SentinelStore(db_path)
        await store.connect()
        try:
            # Must not crash, and should return a strategy dict with `text`.
            strat = await store.get_strategy()
            self.assertIn("text", strat)
            self.assertIsInstance(strat["text"], str)
        finally:
            await store.close()


if __name__ == "__main__":
    unittest.main()

