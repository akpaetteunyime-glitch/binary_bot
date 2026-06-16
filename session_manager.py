import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from contextlib import suppress

from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

from config import AMOUNT, ASSET, EXPIRY_SECONDS, MARTINGALE_LEVELS, MARTINGALE_MULTIPLIER, MIN_PAYOUT, PREFERRED_ASSETS
from database import UserDatabase
from strategies.candle_strategy import CandleColorStrategy
from trading_engine import TradingEngine, AssetSwitchedException


@dataclass
class UserSession:
    telegram_user_id: int
    username: str | None
    client: PocketOptionAsync
    engine: TradingEngine
    candle_task: asyncio.Task | None = None


class SessionManager:
    def __init__(self, db_path: str | None = None):
        self.db = UserDatabase(db_path) if db_path else UserDatabase()
        self.sessions: dict[int, UserSession] = {}

    def _apply_record_to_engine(self, engine: TradingEngine, record: dict):
        engine.asset = record.get("asset") or ASSET
        engine.base_amount = float(record.get("amount") or AMOUNT)
        engine.default_expiry = int(record.get("expiry_seconds") or EXPIRY_SECONDS)
        engine.martingale_levels = int(record.get("martingale_levels") or MARTINGALE_LEVELS)
        engine.martingale_multiplier = float(record.get("martingale_multiplier") or MARTINGALE_MULTIPLIER)
        engine.martingale_enabled = bool(record.get("martingale_enabled", 1))
        engine.martingale_level = int(record.get("martingale_level", 0))
        engine.daily_loss = float(record.get("daily_loss", 0))
        engine.trades_today = int(record.get("trades_today", 0))
        engine.auto_trading = bool(record.get("auto_trading", 0))
        engine.min_payout = int(record.get("min_payout") or MIN_PAYOUT)
        pa = record.get("preferred_assets")
        if pa:
            if isinstance(pa, str):
                engine.preferred_assets = [a.strip() for a in pa.split(",") if a.strip()]
            elif isinstance(pa, list):
                engine.preferred_assets = pa
        else:
            engine.preferred_assets = list(PREFERRED_ASSETS)
        strat_name = record.get("strategy", "CandleColor")
        engine.set_strategy_by_name(strat_name)

    async def _create_session(self, telegram_user_id: int, username: str | None = None) -> UserSession | None:
        record = self.db.get_user(telegram_user_id)
        if not record or not record.get("ssid"):
            return None
        try:
            client = PocketOptionAsync(ssid=record["ssid"])
            await asyncio.wait_for(client.balance(), timeout=10.0)
            engine = TradingEngine(client)
            engine.set_trade_logger(lambda message: self._notify_user(telegram_user_id, message))
            engine.on_martingale_level_changed = lambda level: self._on_martingale_level_changed(telegram_user_id, level)
            self._apply_record_to_engine(engine, record)
            session = UserSession(telegram_user_id=telegram_user_id, username=username or record.get("username"), client=client, engine=engine)
            self.sessions[telegram_user_id] = session
            return session
        except asyncio.TimeoutError:
            print(f"[SESSION] Timeout for {telegram_user_id}")
            await self._notify_user(telegram_user_id, "❌ Connection timeout. Check your SSID.")
            return None
        except Exception as e:
            print(f"[SESSION] Error: {e}")
            await self._notify_user(telegram_user_id, f"❌ Failed to connect: {e}")
            return None

    async def ensure_session(self, telegram_user_id: int, username: str | None = None) -> UserSession | None:
        session = self.sessions.get(telegram_user_id)
        if session:
            if username and session.username != username:
                session.username = username
                self.db.update_fields(telegram_user_id, username=username)
            return session
        return await self._create_session(telegram_user_id, username)

    async def _restart_candle_task(self, session: UserSession):
        await self.stop_auto_trading(session.telegram_user_id, persist=True)
        await self.start_auto_trading(session.telegram_user_id, persist=True)

    async def link_ssid(self, telegram_user_id: int, username: str | None, ssid: str):
        self.db.upsert_user(telegram_user_id, username=username, ssid=ssid)
        if telegram_user_id in self.sessions:
            await self.close_session(telegram_user_id)
        session = await self._create_session(telegram_user_id, username)
        return session is not None

    async def update_user_config(self, telegram_user_id: int, username: str | None, config: dict):
        payload = dict(config)
        ssid = payload.pop("account_ssid", None) or payload.pop("ssid", None)
        if ssid:
            await self.link_ssid(telegram_user_id, username, ssid)
        if payload:
            self.db.update_fields(telegram_user_id, username=username, **payload)
        session = await self.ensure_session(telegram_user_id, username)
        if session:
            self._apply_record_to_engine(session.engine, self.db.get_user(telegram_user_id) or {})
            if session.engine.auto_trading and session.candle_task is None:
                await self.start_auto_trading(telegram_user_id, persist=False)

    async def _notify_user(self, telegram_user_id: int, message: str):
        notifier = getattr(self, "notifier", None)
        if notifier is None:
            print(message)
            return
        try:
            result = notifier(telegram_user_id, message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"Notify error: {e}")

    def set_notifier(self, notifier):
        self.notifier = notifier

    async def close_session(self, telegram_user_id: int):
        session = self.sessions.pop(telegram_user_id, None)
        if not session:
            return
        with suppress(Exception):
            await session.engine.cancel_pending_result_tasks()
        if session.candle_task and not session.candle_task.done():
            session.candle_task.cancel()
            with suppress(asyncio.CancelledError):
                await session.candle_task
        await session.client.disconnect()

    async def _run_candles(self, session: UserSession):
        retry_delay = 5
        max_retries = 3
        retry_count = 0

        while session.engine.auto_trading:
            try:
                current_asset = session.engine.asset
                subscription = await asyncio.wait_for(
                    session.client.subscribe_symbol_time_aligned(current_asset, timedelta(seconds=60)),
                    timeout=30.0
                )
                retry_count = 0
                async for candle in subscription:
                    if not session.engine.auto_trading:
                        break
                    if session.engine.asset != current_asset:
                        print(f"[CANDLE] Asset changed {current_asset} → {session.engine.asset}. Restarting...")
                        break
                    print(f"Candle for {session.telegram_user_id}: O={candle.get('open')} C={candle.get('close')}")
                    await session.engine.on_candle(candle)
            except AssetSwitchedException as e:
                print(f"[CANDLE] Asset switched to {e.args[0] if e.args else '?'}. Restarting subscription.")
                continue
            except asyncio.TimeoutError:
                retry_count += 1
                print(f"[CANDLE] Subscription timeout for {session.engine.asset} (attempt {retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    await self._notify_user(session.telegram_user_id, f"⚠️ No data from {session.engine.asset}. Switching asset...")
                    new_asset = await self._find_fallback_asset(session)
                    if new_asset:
                        await self.set_asset(session.telegram_user_id, session.username, new_asset)
                        retry_count = 0
                    else:
                        await asyncio.sleep(30)
                else:
                    await asyncio.sleep(retry_delay)
            except Exception as e:
                print(f"[CANDLE] Error: {e}")
                await asyncio.sleep(5)

    async def _find_fallback_asset(self, session: UserSession) -> str | None:
        for candidate in session.engine.preferred_assets:
            if candidate == session.engine.asset:
                continue
            try:
                test = await asyncio.wait_for(
                    session.client.subscribe_symbol_time_aligned(candidate, timedelta(seconds=60)),
                    timeout=10.0
                )
                async for _ in test:
                    await test.aclose()
                    return candidate
            except:
                continue
        return None

    async def start_auto_trading(self, telegram_user_id: int, username: str | None = None, persist: bool = True):
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        if session.engine.auto_trading:
            if session.candle_task is None or session.candle_task.done():
                session.candle_task = asyncio.create_task(self._run_candles(session))
            return
        session.engine.start_auto_trading()
        if persist:
            self.db.update_fields(telegram_user_id, username=username, auto_trading=1)
        if session.candle_task is None or session.candle_task.done():
            session.candle_task = asyncio.create_task(self._run_candles(session))

    async def stop_auto_trading(self, telegram_user_id: int, persist: bool = True):
        session = self.sessions.get(telegram_user_id)
        if session:
            if not session.engine.auto_trading and (session.candle_task is None or session.candle_task.done()):
                return
            session.engine.stop_auto_trading()
            if session.candle_task and not session.candle_task.done():
                session.candle_task.cancel()
                with suppress(asyncio.CancelledError):
                    await session.candle_task
            session.candle_task = None
        if persist:
            self.db.update_fields(telegram_user_id, auto_trading=0)

    async def toggle_martingale(self, telegram_user_id: int, username: str | None = None) -> bool:
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        enabled = session.engine.toggle_martingale()
        self.db.update_fields(telegram_user_id, username=username, martingale_enabled=int(enabled), martingale_level=session.engine.martingale_level)
        return enabled

    async def disable_martingale(self, telegram_user_id: int, username: str | None = None):
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        session.engine.disable_martingale()
        self.db.update_fields(telegram_user_id, username=username, martingale_enabled=0, martingale_level=0)

    async def enable_martingale(self, telegram_user_id: int, username: str | None = None):
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        session.engine.enable_martingale()
        self.db.update_fields(telegram_user_id, username=username, martingale_enabled=1)

    async def set_martingale_settings(self, telegram_user_id: int, username: str | None = None, levels: int | None = None, multiplier: float | None = None):
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        session.engine.set_martingale_settings(levels=levels, multiplier=multiplier)
        self.db.update_fields(
            telegram_user_id,
            username=username,
            martingale_levels=session.engine.martingale_levels,
            martingale_multiplier=session.engine.martingale_multiplier,
        )

    async def set_min_payout(self, telegram_user_id: int, username: str | None = None, min_payout: int = 83):
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        session.engine.min_payout = min_payout
        self.db.update_fields(telegram_user_id, username=username, min_payout=min_payout)

    async def apply_manual_config(self, telegram_user_id: int, username: str | None, config: dict):
        await self.update_user_config(telegram_user_id, username, config)

    async def place_trade(self, telegram_user_id: int, direction: str, manual: bool = False, expiry: int | None = None) -> bool:
        session = await self.ensure_session(telegram_user_id)
        if session is None:
            raise ValueError("Link your SSID first")
        return await session.engine.place_trade(direction, manual=manual, expiry=expiry)

    async def get_balance(self, telegram_user_id: int) -> float:
        session = await self.ensure_session(telegram_user_id)
        if session is None:
            raise ValueError("Link your SSID first")
        try:
            balance = await asyncio.wait_for(session.client.balance(), timeout=10.0)
            if isinstance(balance, dict):
                for key in ("balance", "value", "amount"):
                    if key in balance:
                        return float(balance[key])
            return float(balance)
        except asyncio.TimeoutError:
            raise ValueError("Balance check timed out")
        except Exception as e:
            raise ValueError(f"Balance error: {e}")

    async def get_status(self, telegram_user_id: int) -> dict:
        record = self.db.get_user(telegram_user_id) or {}
        session = self.sessions.get(telegram_user_id)
        return {
            "linked": bool(record.get("ssid")),
            "auto_trading": bool((session.engine.auto_trading if session else record.get("auto_trading", 0))),
            "martingale": session.engine.get_martingale_status() if session else "Martingale: OFF",
            "asset": session.engine.asset if session else record.get("asset", ASSET),
            "base_amount": session.engine.base_amount if session else float(record.get("amount", AMOUNT)),
            "default_expiry": session.engine.default_expiry if session else int(record.get("expiry_seconds", EXPIRY_SECONDS)),
            "trades_today": session.engine.trades_today if session else int(record.get("trades_today", 0)),
            "daily_loss": session.engine.daily_loss if session else float(record.get("daily_loss", 0)),
            "min_payout": session.engine.min_payout if session else int(record.get("min_payout", MIN_PAYOUT)),
            "preferred_assets": session.engine.preferred_assets if session else (record.get("preferred_assets") or PREFERRED_ASSETS),
            "strategy": session.engine.strategy_name if session else record.get("strategy", "CandleColor"),
        }

    async def restore_auto_sessions(self):
        active_users = []
        with self.db._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT telegram_user_id, username FROM users WHERE auto_trading = 1 AND ssid IS NOT NULL AND ssid != ''").fetchall()
            active_users = [dict(row) for row in rows]
        for row in active_users:
            try:
                await self.start_auto_trading(int(row["telegram_user_id"]), row.get("username"), persist=False)
            except Exception as e:
                print(f"Could not restore session for {row['telegram_user_id']}: {e}")

    def _on_martingale_level_changed(self, telegram_user_id: int, level: int):
        try:
            self.db.update_fields(telegram_user_id, martingale_level=level)
        except Exception as e:
            print(f"[SESSION] DB error: {e}")

    async def set_asset(self, telegram_user_id: int, username: str | None, new_asset: str) -> bool:
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        success = await session.engine.manual_set_asset(new_asset)
        if success:
            self.db.update_fields(telegram_user_id, username=username, asset=new_asset)
            await self._restart_candle_task(session)
        return success

    async def set_amount(self, telegram_user_id: int, username: str | None, new_amount: float) -> bool:
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        success = await session.engine.set_base_amount(new_amount)
        if success:
            self.db.update_fields(telegram_user_id, username=username, amount=new_amount)
        return success

    async def set_expiry(self, telegram_user_id: int, username: str | None, expiry_seconds: int) -> bool:
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        # The engine method sets the custom expiry flag
        await session.engine.set_default_expiry(expiry_seconds)
        self.db.update_fields(telegram_user_id, username=username, expiry_seconds=expiry_seconds)
        await self._notify_user(telegram_user_id, f"✅ Expiry time set to {expiry_seconds} seconds")
        return True

    async def set_strategy(self, telegram_user_id: int, username: str | None, strategy_name: str) -> bool:
        session = await self.ensure_session(telegram_user_id, username)
        if session is None:
            raise ValueError("Link your SSID first")
        try:
            session.engine.set_strategy_by_name(strategy_name)
            self.db.update_fields(telegram_user_id, username=username, strategy=strategy_name)
            await self._notify_user(telegram_user_id, f"✅ Strategy changed to {strategy_name}")
            return True
        except Exception as e:
            await self._notify_user(telegram_user_id, f"❌ Failed to change strategy: {e}")
            return False