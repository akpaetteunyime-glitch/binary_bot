import asyncio
from contextlib import suppress
from datetime import datetime

from config import AMOUNT, ASSET, EXPIRY_SECONDS, MARTINGALE_LEVELS, MARTINGALE_MULTIPLIER, SCAN_INTERVAL_SECONDS


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
        self.custom_expiry_set = False   # NEW: user has overridden expiry
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
        self.start_scanner()
        print("✅ Auto trading ENABLED")

    def stop_auto_trading(self):
        self.auto_trading = False
        self.stop_scanner()
        print("⏹️ Auto trading DISABLED")

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------
    async def place_trade(self, direction: str, manual: bool = False, expiry: int | None = None) -> bool:
        if not manual and not self.auto_trading:
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
    # Candle handling
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
    # Scanner for EMARSI (unchanged)
    # ------------------------------------------------------------------
    async def _check_asset_condition(self, asset: str) -> bool:
        try:
            candles = await self.client.get_candles(asset, 60, 150)
            if not candles or len(candles) < 100:
                return False
            from strategies.ema_rsi_strategy import EMARSIStrategy
            temp = EMARSIStrategy()
            for c in candles:
                await temp.get_signal(c)
            final_signal = await temp.get_signal(candles[-1])
            return final_signal is not None
        except Exception as e:
            print(f"[SCANNER] Error checking {asset}: {e}")
            return False

    async def _select_best_asset(self) -> str | None:
        for asset in self.preferred_assets:
            if await self._check_asset_condition(asset):
                return asset
        return None

    async def _scanner_loop(self):
        while self.auto_trading:
            try:
                if self.strategy_name != "EMARSI":
                    await asyncio.sleep(self.scan_interval)
                    continue
                print("[SCANNER] Scanning for EMA+RSI conditions...")
                best = await self._select_best_asset()
                if best and best != self.asset:
                    print(f"[SCANNER] Switching to {best}")
                    self.asset = best
                    raise AssetSwitchedException(best)
                elif best == self.asset:
                    print("[SCANNER] Current asset still good.")
                else:
                    print("[SCANNER] No asset meets condition.")
            except AssetSwitchedException:
                raise
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SCANNER] Error: {e}")
            await asyncio.sleep(self.scan_interval)

    def start_scanner(self):
        if self.auto_trading and (self._scanner_task is None or self._scanner_task.done()):
            self._scanner_task = asyncio.create_task(self._scanner_loop())

    def stop_scanner(self):
        if self._scanner_task and not self._scanner_task.done():
            self._scanner_task.cancel()
            self._scanner_task = None