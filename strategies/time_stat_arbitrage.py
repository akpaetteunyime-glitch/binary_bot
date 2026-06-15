from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

class TimeStatArbitrageStrategy:
    expiry_seconds = 60
    lookback_days = 30
    min_trades_per_minute = 5
    min_win_rate = 0.55

    def __init__(self, lookback_days=30, min_trades=5, min_win_rate=0.55):
        self.lookback_days = lookback_days
        self.min_trades_per_minute = min_trades
        self.min_win_rate = min_win_rate
        self.history: dict[int, deque] = defaultdict(lambda: deque(maxlen=lookback_days * 10))
        self.current_day_index = 0
        self.last_date = None

    def _get_day_index(self, dt: datetime) -> int:
        return dt.toordinal()

    def _update_day_index(self, dt: datetime):
        day_idx = self._get_day_index(dt)
        if self.last_date is None or day_idx > self.current_day_index:
            self.current_day_index = day_idx
            self.last_date = dt

    def record_trade_result(self, direction: str, won: bool, candle_time: datetime):
        minute = candle_time.minute
        outcome_key = f"{direction.lower()}_{'win' if won else 'loss'}"
        day_idx = self._get_day_index(candle_time)
        self.history[minute].append((day_idx, outcome_key))
        # prune entries older than lookback_days
        while self.history[minute] and (day_idx - self.history[minute][0][0] > self.lookback_days):
            self.history[minute].popleft()

    def _get_stats(self, minute: int):
        call_wins = call_losses = put_wins = put_losses = 0
        for day_idx, outcome in self.history.get(minute, []):
            if day_idx < self.current_day_index - self.lookback_days:
                continue
            if outcome == 'call_win':
                call_wins += 1
            elif outcome == 'call_loss':
                call_losses += 1
            elif outcome == 'put_win':
                put_wins += 1
            elif outcome == 'put_loss':
                put_losses += 1
        return call_wins, call_losses, put_wins, put_losses

    async def get_signal(self, candle: dict) -> Optional[str]:
        ts = candle.get('time') or candle.get('timestamp')
        if ts is None:
            dt = datetime.now()
        else:
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts)
            else:
                dt = ts

        self._update_day_index(dt)
        minute = dt.minute

        call_wins, call_losses, put_wins, put_losses = self._get_stats(minute)
        call_total = call_wins + call_losses
        put_total = put_wins + put_losses

        call_rate = call_wins / call_total if call_total > 0 else 0.0
        put_rate = put_wins / put_total if put_total > 0 else 0.0

        if call_total >= self.min_trades_per_minute and call_rate >= self.min_win_rate:
            if put_total >= self.min_trades_per_minute:
                return "CALL" if call_rate >= put_rate else "PUT"
            else:
                return "CALL"
        elif put_total >= self.min_trades_per_minute and put_rate >= self.min_win_rate:
            return "PUT"

        return None

    async def get_expiry(self, candle: dict) -> int:
        return self.expiry_seconds