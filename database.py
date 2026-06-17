import sqlite3
from typing import Any
from pathlib import Path
from datetime import date

from config import (
    AMOUNT, ASSET, DATABASE_PATH, EXPIRY_SECONDS,
    MARTINGALE_LEVELS, MARTINGALE_MULTIPLIER, MIN_PAYOUT, PREFERRED_ASSETS,
    ASSET_SCANNER_ENABLED, MIN_PAYOUT_TARGET, PAYOUT_DROP_THRESHOLD,
    MAX_WICK_RATIO, MIN_TREND_SCORE, SCANNER_CHECK_INTERVAL,
)
from ssid_crypto import SSIDCrypto


class UserDatabase:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = Path(db_path)
        self.ssid_crypto = SSIDCrypto()
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    ssid TEXT,
                    asset TEXT NOT NULL,
                    amount REAL NOT NULL,
                    expiry_seconds INTEGER NOT NULL,
                    martingale_levels INTEGER NOT NULL,
                    martingale_multiplier REAL NOT NULL,
                    martingale_enabled INTEGER NOT NULL DEFAULT 1,
                    martingale_level INTEGER NOT NULL DEFAULT 0,
                    auto_trading INTEGER NOT NULL DEFAULT 0,
                    daily_loss REAL NOT NULL DEFAULT 0,
                    trades_today INTEGER NOT NULL DEFAULT 0,
                    min_payout INTEGER NOT NULL DEFAULT 83,
                    preferred_assets TEXT,
                    strategy TEXT DEFAULT 'CandleColor',
                    sessions_enabled INTEGER DEFAULT 0,
                    sessions_per_day INTEGER DEFAULT 3,
                    trades_per_session INTEGER DEFAULT 8,
                    session_start_hour INTEGER DEFAULT 7,
                    session_wins INTEGER DEFAULT 0,
                    session_index INTEGER DEFAULT -1,
                    session_date TEXT,
                    scanner_enabled INTEGER DEFAULT 1,
                    min_payout_target REAL DEFAULT 92.0,
                    payout_drop_threshold REAL DEFAULT 85.0,
                    max_wick_ratio REAL DEFAULT 0.25,
                    min_trend_score REAL DEFAULT 60.0,
                    scanner_check_interval INTEGER DEFAULT 30,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )

            existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}

            migrations = [
                ("ssid", "ALTER TABLE users ADD COLUMN ssid TEXT"),
                ("min_payout", "ALTER TABLE users ADD COLUMN min_payout INTEGER NOT NULL DEFAULT 83"),
                ("preferred_assets", "ALTER TABLE users ADD COLUMN preferred_assets TEXT"),
                ("strategy", "ALTER TABLE users ADD COLUMN strategy TEXT DEFAULT 'CandleColor'"),
                ("sessions_enabled", "ALTER TABLE users ADD COLUMN sessions_enabled INTEGER DEFAULT 0"),
                ("sessions_per_day", "ALTER TABLE users ADD COLUMN sessions_per_day INTEGER DEFAULT 3"),
                ("trades_per_session", "ALTER TABLE users ADD COLUMN trades_per_session INTEGER DEFAULT 8"),
                ("session_start_hour", "ALTER TABLE users ADD COLUMN session_start_hour INTEGER DEFAULT 7"),
                ("session_wins", "ALTER TABLE users ADD COLUMN session_wins INTEGER DEFAULT 0"),
                ("session_index", "ALTER TABLE users ADD COLUMN session_index INTEGER DEFAULT -1"),
                ("session_date", "ALTER TABLE users ADD COLUMN session_date TEXT"),
                ("scanner_enabled", "ALTER TABLE users ADD COLUMN scanner_enabled INTEGER DEFAULT 1"),
                ("min_payout_target", "ALTER TABLE users ADD COLUMN min_payout_target REAL DEFAULT 92.0"),
                ("payout_drop_threshold", "ALTER TABLE users ADD COLUMN payout_drop_threshold REAL DEFAULT 85.0"),
                ("max_wick_ratio", "ALTER TABLE users ADD COLUMN max_wick_ratio REAL DEFAULT 0.25"),
                ("min_trend_score", "ALTER TABLE users ADD COLUMN min_trend_score REAL DEFAULT 60.0"),
                ("scanner_check_interval", "ALTER TABLE users ADD COLUMN scanner_check_interval INTEGER DEFAULT 30"),
            ]

            for column_name, column_sql in migrations:
                if column_name not in existing_columns:
                    conn.execute(column_sql)

            # Encrypt any plaintext SSIDs
            rows_to_encrypt = conn.execute(
                "SELECT telegram_user_id, ssid FROM users WHERE ssid IS NOT NULL AND ssid != '' AND ssid NOT LIKE 'enc:%'"
            ).fetchall()
            for row in rows_to_encrypt:
                conn.execute(
                    "UPDATE users SET ssid = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_user_id = ?",
                    (self.ssid_crypto.encrypt(row[1]), row[0]),
                )

    def get_user(self, telegram_user_id: int):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["ssid"] = self.ssid_crypto.decrypt(result.get("ssid"))
            pa = result.get("preferred_assets")
            if pa:
                result["preferred_assets"] = [a.strip() for a in pa.split(",") if a.strip()]
            else:
                result["preferred_assets"] = list(PREFERRED_ASSETS)
            return result

    def upsert_user(self, telegram_user_id: int, username: str | None = None, **fields):
        """Dynamic upsert that always matches columns to values."""
        current = self.get_user(telegram_user_id) or {}

        def _val(key, default):
            v = fields.get(key, current.get(key, default))
            return v if v is not None else default

        # Build payload dict with all columns that exist in the table
        payload = {
            "telegram_user_id": telegram_user_id,
            "username": username if username is not None else current.get("username"),
            "ssid": self.ssid_crypto.encrypt(fields.get("ssid", current.get("ssid"))),
            "asset": _val("asset", ASSET),
            "amount": _val("amount", AMOUNT),
            "expiry_seconds": _val("expiry_seconds", EXPIRY_SECONDS),
            "martingale_levels": _val("martingale_levels", MARTINGALE_LEVELS),
            "martingale_multiplier": _val("martingale_multiplier", MARTINGALE_MULTIPLIER),
            "martingale_enabled": int(_val("martingale_enabled", 1)),
            "martingale_level": _val("martingale_level", 0),
            "auto_trading": int(_val("auto_trading", 0)),
            "daily_loss": _val("daily_loss", 0),
            "trades_today": _val("trades_today", 0),
            "min_payout": _val("min_payout", MIN_PAYOUT),
            "preferred_assets": _val("preferred_assets", ",".join(PREFERRED_ASSETS)),
            "strategy": _val("strategy", "CandleColor"),
            "sessions_enabled": int(_val("sessions_enabled", 0)),
            "sessions_per_day": int(_val("sessions_per_day", 3)),
            "trades_per_session": int(_val("trades_per_session", 8)),
            "session_start_hour": int(_val("session_start_hour", 7)),
            "session_wins": int(_val("session_wins", 0)),
            "session_index": int(_val("session_index", -1)),
            "session_date": _val("session_date", str(date.today())),
            "scanner_enabled": int(_val("scanner_enabled", 1 if ASSET_SCANNER_ENABLED else 0)),
            "min_payout_target": float(_val("min_payout_target", MIN_PAYOUT_TARGET)),
            "payout_drop_threshold": float(_val("payout_drop_threshold", PAYOUT_DROP_THRESHOLD)),
            "max_wick_ratio": float(_val("max_wick_ratio", MAX_WICK_RATIO)),
            "min_trend_score": float(_val("min_trend_score", MIN_TREND_SCORE)),
            "scanner_check_interval": int(_val("scanner_check_interval", SCANNER_CHECK_INTERVAL)),
        }

        if isinstance(payload["preferred_assets"], list):
            payload["preferred_assets"] = ",".join(payload["preferred_assets"])

        # Remove any None SSID encryption issue
        if payload["ssid"] is None:
            payload["ssid"] = ""

        # Build dynamic SQL to guarantee column/value match
        # Exclude updated_at from payload - let DB handle it via CURRENT_TIMESTAMP
        columns = list(payload.keys())
        placeholders = ["?" for _ in columns]
        values = list(payload.values())

        # Remove updated_at from INSERT columns/values - DB handles it
        if "updated_at" in columns:
            idx = columns.index("updated_at")
            # BUG FIX: must pop from ALL THREE lists
            columns.pop(idx)
            placeholders.pop(idx)
            values.pop(idx)

        sql = f"""
            INSERT INTO users ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                {', '.join(f'{c} = excluded.{c}' for c in columns if c != 'telegram_user_id')},
                updated_at = CURRENT_TIMESTAMP
        """

        with self._connect() as conn:
            conn.execute(sql, values)

    def update_fields(self, telegram_user_id: int, **fields):
        current = self.get_user(telegram_user_id)
        if current is None:
            self.upsert_user(telegram_user_id, **fields)
            return
        merged = dict(current)
        merged.update(fields)
        merged.pop("telegram_user_id", None)
        merged.pop("created_at", None)  # Don't overwrite created_at
        merged.pop("updated_at", None)  # Let DB handle updated_at
        username = merged.pop("username", None)
        self.upsert_user(telegram_user_id, username=username, **merged)

    def migrate_plaintext_ssids(self) -> int:
        count = 0
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT telegram_user_id, ssid FROM users WHERE ssid IS NOT NULL AND ssid != '' AND ssid NOT LIKE 'enc:%'"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE users SET ssid = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_user_id = ?",
                    (self.ssid_crypto.encrypt(row["ssid"]), row["telegram_user_id"]),
                )
                count += 1
        return count

    def has_ssid(self, telegram_user_id: int) -> bool:
        user = self.get_user(telegram_user_id)
        return bool(user and user.get("ssid"))