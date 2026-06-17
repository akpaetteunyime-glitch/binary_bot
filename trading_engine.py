import asyncio
from contextlib import suppress
from datetime import datetime, date, timedelta

from config import (
    AMOUNT, ASSET, EXPIRY_SECONDS, MARTINGALE_LEVELS, MARTINGALE_MULTIPLIER,
    SCAN_INTERVAL_SECONDS,
    MIN_PAYOUT_TARGET, PAYOUT_DROP_THRESHOLD, MAX_WICK_RATIO,
    MIN_TREND_SCORE, SCANNER_CHECK_INTERVAL,
)
from asset_scanner import AssetScanner

class AssetSwitchedException(Exception):
    pass

class TradingEngine:
    def __init__(self, client):
        self.client = client
        self.auto_trading = False
        self.strategy = None
        self.strategy_name = "CandleColor"
        self.trade_logger = None
        self.pending_result_tasks = set()
        self.daily_loss = 0.0
        self.trades_today = 0
        self.default_expiry = EXPIRY_SECONDS
        self.custom_expiry_set = False
        self.asset = ASSET
        self.base_amount = AMOUNT
        self.martingale_levels = MARTINGALE_LEVELS
        self.martingale_multiplier = MARTINGALE_MULTIPLIER
        self.martingale_level = 0
        self.martingale_enabled = True
        self.last_trade_amount = self.base_amount
        self.on_martingale_level_changed = None
        self._result_ready_event = asyncio.Event()
        self._result_ready_event.set()
        self.last_candle_time = None
        self.preferred_assets = []
        self._scanner_task: asyncio.Task | None = None
        self.scan_interval = SCAN_INTERVAL_SECONDS

        # Session scheduling
        self.sessions_enabled = False
        self.sessions_per_day = 3
        self.trades_per_session = 8
        self.session_start_hour = 7
        self.session_wins = 0
        self.session_index = -1
        self.session_date = None
        self.on_session_state_changed = None
        self._all_sessions_done_notified = False

        # Asset scanner
        self.scanner_enabled = False
        self.min_payout_target = MIN_PAYOUT_TARGET
        self.payout_drop_threshold = PAYOUT_DROP_THRESHOLD
        self.max_wick_ratio = MAX_WICK_RATIO
        self.min_trend_score = MIN_TREND_SCORE
        self.scanner_check_interval = SCANNER_CHECK_INTERVAL
        self.scanner = None
        self._scanner_start_count = 0

        # Candle timing (kept for compatibility, unused by old on_candle)
        self._prev_complete_candle: dict | None = None
        self._current_candle_ts: float | None = None
        self._event_cleared_at: datetime | None = None

    # ------------------------------------------------------------------
    # Strategy switching
    # ------------------------------------------------------------------
    def set_strategy_by_name(self, name: str):
        if name == "CandleColor":
            from strategies.candle_strategy import CandleColorStrategy
            self.strategy = CandleColorStrategy()
        elif name == "MACrossover":
            from strategies.ma_crossover_strategy import MACrossoverStrategy
            self.strategy = MACrossoverStrategy()
        elif name == "TimeStatArbitrage":
            self.strategy = self.data_collector
        elif name == "EMARSI":
            from strategies.ema_rsi_strategy import EMARSIStrategy
            self.strategy = EMARSIStrategy()
        elif name == "Rotational":
            from strategies.rotational_strategy import RotationalStrategy
            self.strategy = RotationalStrategy()
        else:
            raise ValueError(f"Unknown strategy {name}")
        self.strategy_name = name
        print(f"[STRATEGY] Switched to {name}")

    # ------------------------------------------------------------------
    # Martingale methods
    # ------------------------------------------------------------------
    def get_current_trade_amount(self) -> float:
        if not self.martingale_enabled:
            return self.base_amount
        return round(self.base_amount * (self.martingale_multiplier ** self.martingale_level), 2)

    def _reset_martingale(self):
        if self.martingale_level != 0:
            print(f"[MARTINGALE] RESET after win: level {self.martingale_level} → 0")
            self.martingale_level = 0
            self._notify_level_change()

    def _advance_martingale(self):
        if not self.martingale_enabled:
            return
        if self.martingale_level < self.martingale_levels - 1:
            self.martingale_level += 1
            print(f"[MARTINGALE] LOSS: advanced to level {self.martingale_level}")
        else:
            print(f"[MARTINGALE] MAX level reached. Resetting.")
            self._reset_martingale()
        self._notify_level_change()

    def _notify_level_change(self):
        if self.on_martingale_level_changed:
            try:
                result = self.on_martingale_level_changed(self.martingale_level)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                print(f"[MARTINGALE] DB error: {e}")

    def toggle_martingale(self) -> bool:
        self.martingale_enabled = not self.martingale_enabled
        if not self.martingale_enabled:
            self._reset_martingale()
        return self.martingale_enabled

    def enable_martingale(self):
        self.martingale_enabled = True

    def disable_martingale(self):
        self.martingale_enabled = False
        self._reset_martingale()

    def set_martingale_settings(self, levels: int | None = None, multiplier: float | None = None):
        if levels is not None:
            if levels < 1:
                raise ValueError("Levels must be at least 1")
            self.martingale_levels = levels
            if self.martingale_level >= self.martingale_levels:
                self._reset_martingale()
        if multiplier is not None:
            if multiplier <= 1:
                raise ValueError("Multiplier must be >1")
            self.martingale_multiplier = multiplier

    def get_martingale_status(self) -> str:
        state = "ON" if self.martingale_enabled else "OFF"
        return f"Martingale: {state} | Step {self.martingale_level+1}/{self.martingale_levels} | Multiplier: {self.martingale_multiplier:.2f} | Next: ${self.get_current_trade_amount():.2f}"

    # ------------------------------------------------------------------
    # Configuration and logging
    # ------------------------------------------------------------------
    def apply_manual_config(self, config: dict) -> dict:
        applied = []
        if "amount" in config:
            self.base_amount = float(config["amount"])
            applied.append(f"amount=${self.base_amount:.2f}")
        if "expiry_seconds" in config:
            self.default_expiry = int(config["expiry_seconds"])
            self.custom_expiry_set = True
            applied.append(f"expiry={self.default_expiry}s")
        if "martingale_levels" in config or "martingale_multiplier" in config:
            self.set_martingale_settings(
                levels=int(config["martingale_levels"]) if "martingale_levels" in config else None,
                multiplier=float(config["martingale_multiplier"]) if "martingale_multiplier" in config else None,
            )
            applied.append("martingale updated")
        if "asset" in config:
            self.asset = str(config["asset"])
            applied.append(f"asset={self.asset}")
        return {"applied": applied, "requires_restart": []}

    async def _emit_trade_log(self, message: str):
        if not self.trade_logger:
            print(message)
            return
        result = self.trade_logger(message)
        if asyncio.iscoroutine(result):
            await result

    def set_strategy(self, strategy):
        self.strategy = strategy

    def set_trade_logger(self, logger):
        self.trade_logger = logger

    def _format_trade_opened(self, direction: str, amount: float, expiry_value: int) -> str:
        prefix = "[IMAGE:up] " if direction == "CALL" else "[IMAGE:down] "
        return prefix + (
            f"📊 Trade Opened\n"
            f"Asset: {self.asset}\n"
            f"Direction: {direction}\n"
            f"Amount: ${amount:.2f}\n"
            f"Expiry: {expiry_value}s"
        )

    def _format_trade_result_win(self, amount: float) -> str:
        return f"[IMAGE:win] 🟢 Trade Result\nAsset: {self.asset}\nResult: WIN\nAmount: ${amount:.2f}"

    def _parse_trade_outcome(self, result) -> str | None:
        if result is None:
            return None
        if isinstance(result, str):
            clean = result.lower().strip()
            if clean in ("win", "w", "true", "1", "yes", "success"):
                return "win"
            if clean in ("loss", "lose", "l", "false", "0", "no", "fail", "failed"):
                return "loss"
            if clean in ("draw", "tie", "equal", "0.0"):
                return "draw"
            return clean
        if isinstance(result, bool):
            return "win" if result else "loss"
        if isinstance(result, (int, float)):
            if result > 0:
                return "win"
            if result < 0:
                return "loss"
            return "draw"
        if isinstance(result, dict):
            for key in ("result", "status", "outcome"):
                val = result.get(key)
                if isinstance(val, str):
                    parsed = self._parse_trade_outcome(val)
                    if parsed:
                        return parsed
            for key in ("win", "won", "success"):
                if result.get(key) is True:
                    return "win"
                if result.get(key) is False:
                    return "loss"
            for key in ("profit", "payout", "pnl"):
                val = result.get(key)
                if val is not None:
                    try:
                        fval = float(val)
                        if fval > 0:
                            return "win"
                        if fval < 0:
                            return "loss"
                    except:
                        pass
        return None

    async def _update_martingale_from_result(self, trade_id: str, amount: float, timeout_seconds: int, direction: str):
        outcome = None
        try:
            result = await self.client.check_win(trade_id, timeout_seconds=timeout_seconds)
            outcome = self._parse_trade_outcome(result)
            print(f"[RESULT] Trade {trade_id} → {outcome}")

            outcome_lower = (outcome or "").lower()
            if outcome_lower == "loss":
                self.daily_loss += amount
                if self.martingale_enabled:
                    self._advance_martingale()
            elif outcome_lower == "win":
                if self.martingale_enabled:
                    self._reset_martingale()
                await self._emit_trade_log(self._format_trade_result_win(amount))
                await self._record_win()
            elif outcome_lower == "draw":
                print("Draw – no message")
            else:
                print(f"Unknown outcome '{outcome}' – no message")

            if hasattr(self, 'data_collector') and self.last_candle_time:
                self.data_collector.record_trade_result(direction, outcome_lower == 'win', self.last_candle_time)
            if hasattr(self.strategy, 'record_trade_result') and self.last_candle_time:
                self.strategy.record_trade_result(direction, outcome_lower == 'win', self.last_candle_time)

        except Exception as e:
            outcome = f"error: {e}"
            print(f"Result error: {e}")
        finally:
            self._result_ready_event.set()
            self._event_cleared_at = None

    def _track_result_task(self, task: asyncio.Task):
        self.pending_result_tasks.add(task)
        task.add_done_callback(lambda t: self.pending_result_tasks.discard(t))

    async def cancel_pending_result_tasks(self):
        for task in list(self.pending_result_tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    # ------------------------------------------------------------------
    # Auto trading control
    # ------------------------------------------------------------------
    def start_auto_trading(self):
        self.auto_trading = True
        self._all_sessions_done_notified = False
        print(f"[ENGINE] start_auto_trading called. scanner_enabled={self.scanner_enabled}")
        if self.scanner_enabled:
            self._init_scanner()
            self.start_scanner()
        else:
            print("[ENGINE] Scanner is disabled. Skipping scanner start.")
        print("✅ Auto trading ENABLED")

    def stop_auto_trading(self):
        self.auto_trading = False
        self.stop_scanner()
        print("⏹️ Auto trading DISABLED")

    # ------------------------------------------------------------------
    # Scanner settings
    # ------------------------------------------------------------------
    def _init_scanner(self):
        print(f"[SCANNER] Initializing scanner: target={self.min_payout_target}%, drop={self.payout_drop_threshold}%, wick={self.max_wick_ratio}, trend={self.min_trend_score}")
        self.scanner = AssetScanner(
            self.client,
            min_payout_target=self.min_payout_target,
            max_wick_ratio=self.max_wick_ratio,
            min_trend_score=self.min_trend_score,
            lookback_candles=20,
        )

    def set_scanner_settings(
        self,
        enabled: bool | None = None,
        min_payout_target: float | None = None,
        payout_drop_threshold: float | None = None,
        max_wick_ratio: float | None = None,
        min_trend_score: float | None = None,
        check_interval: int | None = None,
    ):
        if enabled is not None:
            self.scanner_enabled = enabled
        if min_payout_target is not None:
            self.min_payout_target = min_payout_target
        if payout_drop_threshold is not None:
            self.payout_drop_threshold = payout_drop_threshold
        if max_wick_ratio is not None:
            self.max_wick_ratio = max_wick_ratio
        if min_trend_score is not None:
            self.min_trend_score = min_trend_score
        if check_interval is not None:
            self.scanner_check_interval = check_interval
        if self.scanner:
            self.scanner.min_payout_target = self.min_payout_target
            self.scanner.max_wick_ratio = self.max_wick_ratio
            self.scanner.min_trend_score = self.min_trend_score

    def restart_scanner(self):
        print(f"[SCANNER] restart_scanner called. enabled={self.scanner_enabled}, auto_trading={self.auto_trading}")
        if not self.scanner_enabled:
            print("[SCANNER] Scanner disabled, not restarting.")
            return
        if self.scanner is None:
            self._init_scanner()
        self.stop_scanner()
        if self.auto_trading:
            self.start_scanner()
            print("[SCANNER] Scanner restarted.")
        else:
            print("[SCANNER] Auto trading is off, scanner not started.")

    # ------------------------------------------------------------------
    # Session scheduling methods
    # ------------------------------------------------------------------
    def _get_session_schedule(self, dt: datetime):
        start_hour = self.session_start_hour
        if self.sessions_per_day == 3:
            gap_hours = 5
        elif self.sessions_per_day == 5:
            gap_hours = 3
        elif self.sessions_per_day == 15:
            gap_hours = 1
        else:
            gap_hours = 24 // self.sessions_per_day

        base = dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        sessions = []
        for i in range(self.sessions_per_day):
            start = base + timedelta(hours=i * gap_hours)
            end = start + timedelta(hours=gap_hours) - timedelta(minutes=5)
            sessions.append((start, end))
        return sessions

    def _get_current_session_index(self, dt: datetime):
        sessions = self._get_session_schedule(dt)
        for i, (start, end) in enumerate(sessions):
            if start <= dt < end:
                return i, True
        return -1, False

    def _reset_session_if_needed(self):
        today = str(date.today())
        if self.session_date is None or self.session_date != today:
            self.session_wins = 0
            self.session_index = -1
            self.session_date = today
            self._all_sessions_done_notified = False
            self._notify_session_state_changed()

    def _notify_session_state_changed(self):
        if self.on_session_state_changed:
            try:
                result = self.on_session_state_changed(self.session_wins, self.session_index, self.session_date)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                print(f"[SESSION] DB update error: {e}")

    async def _record_win(self):
        if not self.sessions_enabled:
            return
        self._reset_session_if_needed()
        self.session_wins += 1
        print(f"[SESSION] Win recorded. {self.session_wins}/{self.trades_per_session} this session.")
        self._notify_session_state_changed()
        if self.session_wins >= self.trades_per_session:
            print(f"[SESSION] Session completed!")
            await self._emit_trade_log(f"✅ Session completed! {self.session_wins} wins reached.")
            if self.session_index == self.sessions_per_day - 1:
                print("[SESSION] All daily sessions completed. Stopping auto trading.")
                if not self._all_sessions_done_notified:
                    await self._emit_trade_log("🏁 All sessions completed for today. Auto trading stopped.")
                    self._all_sessions_done_notified = True
                self.stop_auto_trading()

    def can_trade(self) -> bool:
        if not self.sessions_enabled:
            return True
        dt = datetime.now()
        self._reset_session_if_needed()
        idx, active = self._get_current_session_index(dt)

        if idx == -1 and self.session_index == self.sessions_per_day - 1 and self.session_wins >= self.trades_per_session:
            if not self._all_sessions_done_notified:
                print("[SESSION] All sessions completed for today.")
            return False

        if not active:
            print("[SESSION] Not in an active session window.")
            return False
        if idx != self.session_index:
            self.session_wins = 0
            self.session_index = idx
            self._notify_session_state_changed()
            print(f"[SESSION] New session started. Wins this session: 0/{self.trades_per_session}")
        if self.session_wins >= self.trades_per_session:
            print(f"[SESSION] Win limit ({self.trades_per_session}) reached for this session.")
            return False
        return True

    async def set_session_settings(self, enabled: bool = None, sessions_per_day: int = None,
                                   trades_per_session: int = None, start_hour: int = None):
        if enabled is not None:
            self.sessions_enabled = enabled
        if sessions_per_day is not None:
            self.sessions_per_day = sessions_per_day
        if trades_per_session is not None:
            self.trades_per_session = trades_per_session
        if start_hour is not None:
            self.session_start_hour = start_hour
        self.session_wins = 0
        self.session_index = -1
        self.session_date = str(date.today())
        self._all_sessions_done_notified = False
        self._notify_session_state_changed()
        print(f"[SESSION] Settings updated: enabled={self.sessions_enabled}, "
              f"sessions={self.sessions_per_day}, trades={self.trades_per_session}, start_hour={self.session_start_hour}")

    # ------------------------------------------------------------------
    # Trade execution  — REVERTED TO WORKING REPO VERSION
    # ------------------------------------------------------------------
    async def place_trade(self, direction: str, manual: bool = False, expiry: int | None = None) -> bool:
        if not manual and not self.auto_trading:
            return False
        # Session check for auto trades only
        if not manual and not self.can_trade():
            await self._emit_trade_log("⏸️ Trading paused: session limit reached or not in session.")
            return False
        try:
            expiry_value = expiry or self.default_expiry
            amount = self.base_amount if manual else self.get_current_trade_amount()
            dir_up = direction.upper()
            if dir_up == "CALL":
                trade_id, _ = await self.client.buy(self.asset, amount, expiry_value)
            elif dir_up == "PUT":
                trade_id, _ = await self.client.sell(self.asset, amount, expiry_value)
            else:
                raise ValueError(f"Invalid direction: {direction}")
            self.trades_today += 1
            await self._emit_trade_log(self._format_trade_opened(dir_up, amount, expiry_value))
            task = asyncio.create_task(self._update_martingale_from_result(trade_id, amount, expiry_value + 15, dir_up))
            self._track_result_task(task)
            return True
        except Exception as e:
            error_msg = f"⚠️ Trade error: {e}"
            print(error_msg)
            await self._emit_trade_log(error_msg)
            return False

    # ------------------------------------------------------------------
    # Manual settings
    # ------------------------------------------------------------------
    async def manual_set_asset(self, new_asset: str) -> bool:
        self.asset = new_asset
        print(f"[MANUAL] Asset changed to {new_asset}, martingale level {self.martingale_level}")
        return True

    async def set_base_amount(self, new_amount: float) -> bool:
        self.base_amount = new_amount
        print(f"[MANUAL] Base amount set to ${new_amount:.2f}")
        return True

    async def set_default_expiry(self, expiry: int):
        self.default_expiry = expiry
        self.custom_expiry_set = True
        print(f"[MANUAL] Expiry set to {expiry}s")

    # ------------------------------------------------------------------
    # Candle handling — REVERTED TO WORKING REPO VERSION
    # ------------------------------------------------------------------
    async def on_candle(self, candle: dict):
        if not self.auto_trading or not self.strategy:
            return
        if not self._result_ready_event.is_set():
            print("[CANDLE] Waiting for previous trade result")
            return

        ts = candle.get('time') or candle.get('timestamp')
        if ts is None:
            self.last_candle_time = datetime.now()
        else:
            if isinstance(ts, (int, float)):
                self.last_candle_time = datetime.fromtimestamp(ts)
            else:
                self.last_candle_time = ts

        # Determine expiry: use custom if set, else strategy's default
        if self.custom_expiry_set:
            expiry = self.default_expiry
        else:
            if hasattr(self.strategy, "get_expiry"):
                exp = await self.strategy.get_expiry(candle)
                expiry = exp if exp is not None else self.default_expiry
            else:
                expiry = self.default_expiry

        signal = await self.strategy.get_signal(candle)
        if signal:
            self._result_ready_event.clear()
            try:
                await self.place_trade(signal, manual=False, expiry=expiry)
            except Exception as e:
                print(f"[CANDLE] Trade error: {e}")
                self._result_ready_event.set()

    # ------------------------------------------------------------------
    # Universal Asset Scanner
    # ------------------------------------------------------------------
    async def _scanner_loop(self):
        print(f"[SCANNER] 🔥 Scanner loop STARTED. scanner_enabled={self.scanner_enabled}, interval={self.scanner_check_interval}s")
        loop_count = 0
        while self.auto_trading:
            try:
                if not self.scanner_enabled or self.scanner is None:
                    print(f"[SCANNER] Scanner disabled or not initialized. enabled={self.scanner_enabled}, scanner={self.scanner}")
                    await asyncio.sleep(5)
                    continue

                loop_count += 1
                if loop_count % 10 == 0:
                    print(f"[SCANNER] Heartbeat: alive after {loop_count} checks, asset={self.asset}")

                print(f"[SCANNER] [{loop_count}] Checking current asset: {self.asset}")
                ok, payout, trend_score, wick_score, momentum_score = await self.scanner.check_current_asset(self.asset)

                if ok and payout >= self.min_payout_target:
                    print(f"[SCANNER] {self.asset} OK | payout={payout:.0f}% trend={trend_score:.0f} wicks={wick_score:.0f} mom={momentum_score:.0f}")
                    await asyncio.sleep(self.scanner_check_interval)
                    continue

                print(f"[SCANNER] {self.asset} DEGRADED | payout={payout:.0f}% trend={trend_score:.0f} wicks={wick_score:.0f} mom={momentum_score:.0f}")
                await self._emit_trade_log(
                    f"⚠️ {self.asset} degraded (payout {payout:.0f}%, trend {trend_score:.0f}). Scanning for better asset..."
                )

                print(f"[SCANNER] Scanning {len(self.preferred_assets)} assets for better candidate...")
                best = await self.scanner.find_best_asset(self.preferred_assets, current_asset=self.asset)
                if best:
                    msg = (
                        f"🔄 Auto-switched to {best.asset}\n"
                        f"Payout: {best.payout:.0f}% | Trend: {best.trend_direction} {best.trend_score:.0f}\n"
                        f"Wicks: {best.wick_score:.0f} | Momentum: {best.momentum_score:.0f}"
                    )
                    print(f"[SCANNER] Switching → {best.asset} | {best.reason}")
                    await self._emit_trade_log(msg)
                    self.asset = best.asset
                    print("[SCANNER] Asset switched. Continuing scanner loop...")
                    await asyncio.sleep(2)
                    continue
                else:
                    print("[SCANNER] No better asset found. Keeping current.")
                    await self._emit_trade_log("❌ No better asset found. Keeping current.")
                    await asyncio.sleep(self.scanner_check_interval)

            except asyncio.CancelledError:
                print("[SCANNER] Scanner loop cancelled.")
                break
            except Exception as e:
                print(f"[SCANNER] ERROR in scanner loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(self.scanner_check_interval)
        print(f"[SCANNER] Scanner loop ENDED. auto_trading={self.auto_trading}")

    def start_scanner(self):
        print(f"[SCANNER] start_scanner called. task_exists={self._scanner_task is not None}, task_done={self._scanner_task.done() if self._scanner_task else 'N/A'}")
        if self.auto_trading and (self._scanner_task is None or self._scanner_task.done()):
            self._scanner_start_count += 1
            print(f"[SCANNER] Creating scanner task (start #{self._scanner_start_count})...")
            self._scanner_task = asyncio.create_task(self._scanner_loop())
            print(f"[SCANNER] Scanner task created: {self._scanner_task}")
        else:
            print(f"[SCANNER] Skipping start: auto_trading={self.auto_trading}, task_exists={self._scanner_task is not None}, task_done={self._scanner_task.done() if self._scanner_task else 'N/A'}")

    def stop_scanner(self):
        print(f"[SCANNER] stop_scanner called.")
        if self._scanner_task and not self._scanner_task.done():
            self._scanner_task.cancel()
            print("[SCANNER] Scanner task cancelled.")
        self._scanner_task = None