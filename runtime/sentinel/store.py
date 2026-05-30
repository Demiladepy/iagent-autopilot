"""SQLite persistence via aiosqlite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from sentinel.schemas import (
    AuditNote,
    Execution,
    MarketEvent,
    Proposal,
    RiskVerdict,
    StrategyConfig,
)

SCHEMA_VERSION = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SentinelStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self.kill_switch_active: bool = False

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._migrate()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def _migrate(self) -> None:
        assert self._db is not None
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS market_events (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                market TEXT NOT NULL,
                payload TEXT NOT NULL,
                source TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                market TEXT,
                side TEXT,
                notional_usd REAL,
                leverage REAL,
                reasoning TEXT NOT NULL,
                confidence REAL NOT NULL,
                expected_hold_hours REAL,
                invalidation TEXT
            );

            CREATE TABLE IF NOT EXISTS risk_verdicts (
                proposal_id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                approved INTEGER NOT NULL,
                reasons TEXT NOT NULL,
                modified_notional REAL,
                modified_leverage REAL
            );

            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                status TEXT NOT NULL,
                tx_hash TEXT,
                tool_called TEXT,
                tool_args TEXT,
                tool_result TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_notes (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                summary TEXT NOT NULL,
                flags TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                text TEXT NOT NULL DEFAULT '',
                max_notional_usd REAL NOT NULL DEFAULT 1000,
                max_leverage REAL NOT NULL DEFAULT 10,
                max_daily_loss_usd REAL NOT NULL DEFAULT 500,
                allowed_markets TEXT NOT NULL DEFAULT '["BTC","ETH","INJ"]',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                opened_at TEXT,
                closed_at TEXT,
                pnl_usd REAL,
                lesson TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_market_events_ts ON market_events(ts);
            CREATE INDEX IF NOT EXISTS idx_proposals_ts ON proposals(ts);
            CREATE INDEX IF NOT EXISTS idx_executions_ts ON executions(ts);
            """
        )
        # Self-heal old DBs where CREATE TABLE IF NOT EXISTS preserved stale schemas.
        await self._ensure_core_table_schemas()
        await self._upgrade_journal_schema()
        await self._db.execute(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        await self._db.execute(
            """
            INSERT OR IGNORE INTO strategy (
                id, text, max_notional_usd, max_leverage, max_daily_loss_usd,
                allowed_markets, updated_at
            ) VALUES (1, '', 1000, 10, 500, '["BTC","ETH","INJ"]', ?)
            """,
            (_dt_to_str(_utc_now()),),
        )
        await self._db.commit()

    async def _ensure_core_table_schemas(self) -> None:
        """
        Idempotent, self-healing migrations.

        SQLite's CREATE TABLE IF NOT EXISTS does not add new columns to existing tables.
        If a user has an older DB on disk, we must ALTER TABLE ADD COLUMN for any
        missing columns that current code reads/writes.
        """
        assert self._db is not None

        await self._ensure_table_columns(
            "strategy",
            {
                # Full set used by get_strategy/set_strategy and seed insert.
                "text": "TEXT NOT NULL DEFAULT ''",
                "max_notional_usd": "REAL NOT NULL DEFAULT 1000",
                "max_leverage": "REAL NOT NULL DEFAULT 10",
                "max_daily_loss_usd": "REAL NOT NULL DEFAULT 500",
                "allowed_markets": "TEXT NOT NULL DEFAULT '[\"BTC\",\"ETH\",\"INJ\"]'",
                "updated_at": "TEXT",
            },
        )

        # Defensive: ensure other tables have the columns we persist (future-proofing).
        await self._ensure_table_columns(
            "market_events",
            {
                "id": "TEXT",
                "ts": "TEXT",
                "kind": "TEXT",
                "market": "TEXT",
                "payload": "TEXT",
                "source": "TEXT",
            },
        )
        await self._ensure_table_columns(
            "proposals",
            {
                "id": "TEXT",
                "event_id": "TEXT",
                "ts": "TEXT",
                "action": "TEXT",
                "market": "TEXT",
                "side": "TEXT",
                "notional_usd": "REAL",
                "leverage": "REAL",
                "reasoning": "TEXT",
                "confidence": "REAL",
                "expected_hold_hours": "REAL",
                "invalidation": "TEXT",
            },
        )
        await self._ensure_table_columns(
            "risk_verdicts",
            {
                "proposal_id": "TEXT",
                "ts": "TEXT",
                "approved": "INTEGER",
                "reasons": "TEXT",
                "modified_notional": "REAL",
                "modified_leverage": "REAL",
            },
        )
        await self._ensure_table_columns(
            "executions",
            {
                "id": "TEXT",
                "proposal_id": "TEXT",
                "ts": "TEXT",
                "status": "TEXT",
                "tx_hash": "TEXT",
                "tool_called": "TEXT",
                "tool_args": "TEXT",
                "tool_result": "TEXT",
                "error": "TEXT",
            },
        )
        await self._ensure_table_columns(
            "audit_notes",
            {
                "id": "TEXT",
                "execution_id": "TEXT",
                "ts": "TEXT",
                "summary": "TEXT",
                "flags": "TEXT",
            },
        )
        await self._ensure_table_columns(
            "journal",
            {
                "id": "INTEGER",
                "execution_id": "TEXT",
                "opened_at": "TEXT",
                "closed_at": "TEXT",
                "pnl_usd": "REAL",
                "lesson": "TEXT",
            },
        )
        await self._db.commit()

    async def _ensure_table_columns(self, table: str, required: dict[str, str]) -> None:
        assert self._db is not None
        # If the table doesn't exist, CREATE TABLE above will have created it.
        async with self._db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
        existing = {row[1] for row in rows}  # row[1] is the column name
        for col, ddl in required.items():
            if col in existing:
                continue
            await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    async def _upgrade_journal_schema(self) -> None:
        """Add journal columns when upgrading from older DB files."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='journal'"
        ) as cursor:
            if not await cursor.fetchone():
                return

        async with self._db.execute("PRAGMA table_info(journal)") as cursor:
            rows = await cursor.fetchall()
        columns = {row[1] for row in rows}

        alters: list[str] = []
        if "opened_at" not in columns:
            alters.append("ALTER TABLE journal ADD COLUMN opened_at TEXT")
        if "closed_at" not in columns:
            alters.append("ALTER TABLE journal ADD COLUMN closed_at TEXT")
        if "pnl_usd" not in columns:
            alters.append("ALTER TABLE journal ADD COLUMN pnl_usd REAL")
        if "lesson" not in columns:
            alters.append("ALTER TABLE journal ADD COLUMN lesson TEXT")

        for sql in alters:
            await self._db.execute(sql)

        if "closed_at" in columns or alters:
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_journal_closed_at ON journal(closed_at)"
            )
        await self._db.commit()

    # --- Writes ---

    async def save_event(self, event: MarketEvent) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO market_events (id, ts, kind, market, payload, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                _dt_to_str(event.ts),
                event.kind,
                event.market,
                json.dumps(event.payload),
                event.source,
            ),
        )
        await self._db.commit()

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT id, ts, kind, market, payload, source FROM market_events WHERE id = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "ts": row["ts"],
            "kind": row["kind"],
            "market": row["market"],
            "payload": json.loads(row["payload"]),
            "source": row["source"],
        }

    async def get_verdict(self, proposal_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            """SELECT proposal_id, ts, approved, reasons, modified_notional, modified_leverage
               FROM risk_verdicts WHERE proposal_id = ?""",
            (proposal_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "proposal_id": row["proposal_id"],
            "ts": row["ts"],
            "approved": bool(row["approved"]),
            "reasons": json.loads(row["reasons"] or "[]"),
            "modified_notional": row["modified_notional"],
            "modified_leverage": row["modified_leverage"],
        }

    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM executions WHERE id = ?",
            (execution_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            **dict(row),
            "tool_args": json.loads(row["tool_args"]) if row["tool_args"] else None,
            "tool_result": json.loads(row["tool_result"]) if row["tool_result"] else None,
        }

    async def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM proposals WHERE id = ?",
            (proposal_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def has_proposal_for_event(self, event_id: str) -> bool:
        assert self._db is not None
        async with self._db.execute(
            "SELECT 1 FROM proposals WHERE event_id = ? LIMIT 1",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def save_proposal(self, proposal: Proposal) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO proposals (
                id, event_id, ts, action, market, side, notional_usd, leverage,
                reasoning, confidence, expected_hold_hours, invalidation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                proposal.id,
                proposal.event_id,
                _dt_to_str(proposal.ts),
                proposal.action,
                proposal.market,
                proposal.side,
                proposal.notional_usd,
                proposal.leverage,
                proposal.reasoning,
                proposal.confidence,
                proposal.expected_hold_hours,
                proposal.invalidation,
            ),
        )
        await self._db.commit()

    async def save_verdict(self, verdict: RiskVerdict) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO risk_verdicts (
                proposal_id, ts, approved, reasons, modified_notional, modified_leverage
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                verdict.proposal_id,
                _dt_to_str(verdict.ts),
                1 if verdict.approved else 0,
                json.dumps(verdict.reasons),
                verdict.modified_notional,
                verdict.modified_leverage,
            ),
        )
        await self._db.commit()

    async def save_execution(self, execution: Execution) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO executions (
                id, proposal_id, ts, status, tx_hash, tool_called, tool_args, tool_result, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution.id,
                execution.proposal_id,
                _dt_to_str(execution.ts),
                execution.status,
                execution.tx_hash,
                execution.tool_called,
                json.dumps(execution.tool_args) if execution.tool_args is not None else None,
                json.dumps(execution.tool_result) if execution.tool_result is not None else None,
                execution.error,
            ),
        )
        await self._db.commit()

    async def save_audit(self, note: AuditNote) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO audit_notes (id, execution_id, ts, summary, flags)
               VALUES (?, ?, ?, ?, ?)""",
            (
                note.id,
                note.execution_id,
                _dt_to_str(note.ts),
                note.summary,
                json.dumps(note.flags),
            ),
        )
        await self._db.commit()

    async def save_journal_entry(
        self,
        *,
        execution_id: str,
        opened_at: datetime | None = None,
        closed_at: datetime | None = None,
        pnl_usd: float | None = None,
        lesson: str | None = None,
    ) -> int:
        assert self._db is not None
        cursor = await self._db.execute(
            """INSERT INTO journal (execution_id, opened_at, closed_at, pnl_usd, lesson)
               VALUES (?, ?, ?, ?, ?)""",
            (
                execution_id,
                _dt_to_str(opened_at) if opened_at else None,
                _dt_to_str(closed_at) if closed_at else None,
                pnl_usd,
                lesson,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    # --- Strategy ---

    async def get_strategy(self) -> dict[str, Any]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT id, text, max_notional_usd, max_leverage, max_daily_loss_usd,
                      allowed_markets, updated_at FROM strategy WHERE id = 1"""
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            cfg = StrategyConfig(updated_at=_utc_now())
            return cfg.model_dump()
        return {
            "id": row["id"],
            "text": row["text"],
            "max_notional_usd": row["max_notional_usd"],
            "max_leverage": row["max_leverage"],
            "max_daily_loss_usd": row["max_daily_loss_usd"],
            "allowed_markets": json.loads(row["allowed_markets"]),
            "updated_at": row["updated_at"],
        }

    async def set_strategy(
        self,
        *,
        text: str | None = None,
        max_notional_usd: float | None = None,
        max_leverage: float | None = None,
        max_daily_loss_usd: float | None = None,
        allowed_markets: list[str] | None = None,
    ) -> dict[str, Any]:
        assert self._db is not None
        current = await self.get_strategy()
        updated = {
            "text": text if text is not None else current["text"],
            "max_notional_usd": (
                max_notional_usd
                if max_notional_usd is not None
                else current["max_notional_usd"]
            ),
            "max_leverage": (
                max_leverage if max_leverage is not None else current["max_leverage"]
            ),
            "max_daily_loss_usd": (
                max_daily_loss_usd
                if max_daily_loss_usd is not None
                else current["max_daily_loss_usd"]
            ),
            "allowed_markets": (
                allowed_markets
                if allowed_markets is not None
                else current["allowed_markets"]
            ),
            "updated_at": _dt_to_str(_utc_now()),
        }
        await self._db.execute(
            """UPDATE strategy SET text = ?, max_notional_usd = ?, max_leverage = ?,
               max_daily_loss_usd = ?, allowed_markets = ?, updated_at = ? WHERE id = 1""",
            (
                updated["text"],
                updated["max_notional_usd"],
                updated["max_leverage"],
                updated["max_daily_loss_usd"],
                json.dumps(updated["allowed_markets"]),
                updated["updated_at"],
            ),
        )
        await self._db.commit()
        return {**current, **updated}

    # --- Reads ---

    async def position_baselines_from_journal(self, limit: int = 50) -> dict[str, float]:
        """Map ``{market:side}`` → opening quantity from journal + execution tool_args."""
        assert self._db is not None
        baselines: dict[str, float] = {}
        async with self._db.execute(
            """SELECT j.lesson, e.tool_args
               FROM journal j
               LEFT JOIN executions e ON e.id = j.execution_id
               ORDER BY j.id DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            tool_args = row["tool_args"]
            if tool_args:
                try:
                    args = json.loads(tool_args)
                    symbol = args.get("symbol") or args.get("market")
                    side = args.get("side")
                    qty = args.get("quantity") or args.get("amount")
                    if symbol and side and qty is not None:
                        key = f"{symbol}:{side}".upper()
                        if key not in baselines:
                            baselines[key] = float(qty)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            lesson = row["lesson"] or ""
            if lesson.startswith("Opened "):
                # e.g. "Opened long BTC $50" — store notional baseline
                parts = lesson.split()
                if len(parts) >= 4:
                    side = parts[1].lower()
                    market = parts[2].upper()
                    key = f"{market}:{side}"
                    if key not in baselines:
                        try:
                            baselines[key] = float(parts[3].replace("$", ""))
                        except ValueError:
                            pass
        return baselines

    async def recent_journal(self, n: int = 10) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT id, execution_id, opened_at, closed_at, pnl_usd, lesson
               FROM journal ORDER BY id DESC LIMIT ?""",
            (n,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def today_pnl(self) -> float:
        assert self._db is not None
        today = _utc_now().date().isoformat()
        async with self._db.execute(
            """SELECT COALESCE(SUM(pnl_usd), 0) AS total FROM journal
               WHERE closed_at IS NOT NULL AND date(closed_at) = ?""",
            (today,),
        ) as cursor:
            row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0

    async def recent_market_events(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT id, ts, kind, market, payload, source FROM market_events
               ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "kind": r["kind"],
                "market": r["market"],
                "payload": json.loads(r["payload"]),
                "source": r["source"],
            }
            for r in rows
        ]

    async def recent_proposals(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT * FROM proposals ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def recent_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT * FROM executions ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                **dict(r),
                "tool_args": json.loads(r["tool_args"]) if r["tool_args"] else None,
                "tool_result": json.loads(r["tool_result"]) if r["tool_result"] else None,
            }
            for r in rows
        ]

    async def get_execution_for_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM executions WHERE proposal_id = ? ORDER BY ts DESC LIMIT 1",
            (proposal_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            **dict(row),
            "tool_args": json.loads(row["tool_args"]) if row["tool_args"] else None,
            "tool_result": json.loads(row["tool_result"]) if row["tool_result"] else None,
        }

    async def get_audit_for_execution(self, execution_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            """SELECT id, execution_id, ts, summary, flags FROM audit_notes
               WHERE execution_id = ? ORDER BY ts DESC LIMIT 1""",
            (execution_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "execution_id": row["execution_id"],
            "ts": row["ts"],
            "summary": row["summary"],
            "flags": json.loads(row["flags"]),
        }

    async def get_last_audit(self) -> dict[str, Any] | None:
        notes = await self.recent_audit_notes(limit=1)
        return notes[0] if notes else None

    async def recent_decision_chains(self, limit: int = 50) -> list[dict[str, Any]]:
        """Join proposal → verdict → execution → audit for dashboard feed."""
        proposals = await self.recent_proposals(limit)
        chains: list[dict[str, Any]] = []
        for proposal in proposals:
            pid = proposal["id"]
            verdict = await self.get_verdict(pid)
            execution = await self.get_execution_for_proposal(pid)
            audit = None
            if execution:
                audit = await self.get_audit_for_execution(execution["id"])
            event = None
            if proposal.get("event_id"):
                event = await self.get_event(str(proposal["event_id"]))
            chains.append(
                {
                    "proposal_id": pid,
                    "event": event,
                    "proposal": proposal,
                    "verdict": verdict,
                    "execution": execution,
                    "audit": audit,
                }
            )
        return chains

    async def recent_audit_notes(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """SELECT id, execution_id, ts, summary, flags FROM audit_notes
               ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "execution_id": r["execution_id"],
                "ts": r["ts"],
                "summary": r["summary"],
                "flags": json.loads(r["flags"]),
            }
            for r in rows
        ]

    # --- Model loaders (optional convenience) ---

    def market_event_from_row(self, row: dict[str, Any]) -> MarketEvent:
        return MarketEvent(
            id=row["id"],
            ts=_str_to_dt(row["ts"]),
            kind=row["kind"],
            market=row["market"],
            payload=row.get("payload") if isinstance(row.get("payload"), dict) else json.loads(row["payload"]),
            source=row["source"],
        )
