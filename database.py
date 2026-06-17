import sqlite3
from typing import Any
from pathlib import Path
from datetime import date

from config import AMOUNT, ASSET, DATABASE_PATH, EXPIRY_SECONDS, MARTINGALE_LEVELS, MARTINGALE_MULTIPLIER, MIN_PAYOUT, PREFERRED_ASSETS
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
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )

            existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            for column_name, column_sql in (
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
            ):
                if column_name not in existing_columns:
                    conn.execute(column_sql)

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
        current = self.get_user(telegram_user_id) or {}
        payload = {
            "telegram_user_id": telegram_user_id,
            "username": username if username is not None else current.get("username"),
            "ssid": self.ssid_crypto.encrypt(fields.get("ssid", current.get("ssid"))),
            "asset": fields.get("asset", current.get("asset", ASSET)),
            "amount": fields.get("amount", current.get("amount", AMOUNT)),
            "expiry_seconds": fields.get("expiry_seconds", current.get("expiry_seconds", EXPIRY_SECONDS)),
            "martingale_levels": fields.get("martingale_levels", current.get("martingale_levels", MARTINGALE_LEVELS)),
            "martingale_multiplier": fields.get("martingale_multiplier", current.get("martingale_multiplier", MARTINGALE_MULTIPLIER)),
            "martingale_enabled": int(fields.get("martingale_enabled", current.get("martingale_enabled", 1))),
            "martingale_level": fields.get("martingale_level", current.get("martingale_level", 0)),
            "auto_trading": int(fields.get("auto_trading", current.get("auto_trading", 0))),
            "daily_loss": fields.get("daily_loss", current.get("daily_loss", 0)),
            "trades_today": fields.get("trades_today", current.get("trades_today", 0)),
            "min_payout": fields.get("min_payout", current.get("min_payout", MIN_PAYOUT)),
            "preferred_assets": fields.get("preferred_assets", current.get("preferred_assets", ",".join(PREFERRED_ASSETS))),
            "strategy": fields.get("strategy", current.get("strategy", "CandleColor")),
            "sessions_enabled": int(fields.get("sessions_enabled", current.get("sessions_enabled", 0))),
            "sessions_per_day": int(fields.get("sessions_per_day", current.get("sessions_per_day", 3))),
            "trades_per_session": int(fields.get("trades_per_session", current.get("trades_per_session", 8))),
            "session_start_hour": int(fields.get("session_start_hour", current.get("session_start_hour", 7))),
            "session_wins": int(fields.get("session_wins", current.get("session_wins", 0))),
            "session_index": int(fields.get("session_index", current.get("session_index", -1))),
            "session_date": fields.get("session_date", current.get("session_date", str(date.today()))),
        }

        if isinstance(payload["preferred_assets"], list):
            payload["preferred_assets"] = ",".join(payload["preferred_assets"])

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id, username, ssid, asset, amount, expiry_seconds,
                    martingale_levels, martingale_multiplier, martingale_enabled,
                    martingale_level, auto_trading, daily_loss, trades_today,
                    min_payout, preferred_assets, strategy,
                    sessions_enabled, sessions_per_day, trades_per_session,
                    session_start_hour, session_wins, session_index, session_date,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username = excluded.username,
                    ssid = excluded.ssid,
                    asset = excluded.asset,
                    amount = excluded.amount,
                    expiry_seconds = excluded.expiry_seconds,
                    martingale_levels = excluded.martingale_levels,
                    martingale_multiplier = excluded.martingale_multiplier,
                    martingale_enabled = excluded.martingale_enabled,
                    martingale_level = excluded.martingale_level,
                    auto_trading = excluded.auto_trading,
                    daily_loss = excluded.daily_loss,
                    trades_today = excluded.trades_today,
                    min_payout = excluded.min_payout,
                    preferred_assets = excluded.preferred_assets,
                    strategy = excluded.strategy,
                    sessions_enabled = excluded.sessions_enabled,
                    sessions_per_day = excluded.sessions_per_day,
                    trades_per_session = excluded.trades_per_session,
                    session_start_hour = excluded.session_start_hour,
                    session_wins = excluded.session_wins,
                    session_index = excluded.session_index,
                    session_date = excluded.session_date,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    payload["telegram_user_id"],
                    payload["username"],
                    payload["ssid"],
                    payload["asset"],
                    payload["amount"],
                    payload["expiry_seconds"],
                    payload["martingale_levels"],
                    payload["martingale_multiplier"],
                    payload["martingale_enabled"],
                    payload["martingale_level"],
                    payload["auto_trading"],
                    payload["daily_loss"],
                    payload["trades_today"],
                    payload["min_payout"],
                    payload["preferred_assets"],
                    payload["strategy"],
                    payload["sessions_enabled"],
                    payload["sessions_per_day"],
                    payload["trades_per_session"],
                    payload["session_start_hour"],
                    payload["session_wins"],
                    payload["session_index"],
                    payload["session_date"],
                ),
            )

    def update_fields(self, telegram_user_id: int, **fields):
        current = self.get_user(telegram_user_id)
        if current is None:
            self.upsert_user(telegram_user_id, **fields)
            return
        merged = dict(current)
        merged.update(fields)
        merged.pop("telegram_user_id", None)
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