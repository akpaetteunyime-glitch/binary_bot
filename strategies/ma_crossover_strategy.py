class MACrossoverStrategy:
    expiry_seconds = 60
    short_period = 2
    long_period = 5

    def __init__(self, short_period=2, long_period=5):
        self.short_period = short_period
        self.long_period = long_period
        self.candle_history = []

    async def get_signal(self, candle: dict) -> str | None:
        close = float(candle['close'])
        self.candle_history.append(close)
        max_len = max(self.short_period, self.long_period) + 1
        if len(self.candle_history) > max_len:
            self.candle_history.pop(0)

        if len(self.candle_history) < max_len:
            return None

        short_ma = sum(self.candle_history[-self.short_period:]) / self.short_period
        long_ma = sum(self.candle_history[-self.long_period:]) / self.long_period

        prev_short = sum(self.candle_history[-self.short_period-1:-1]) / self.short_period
        prev_long = sum(self.candle_history[-self.long_period-1:-1]) / self.long_period

        if prev_short >= prev_long and short_ma < long_ma:
            return "CALL"
        elif prev_short <= prev_long and short_ma > long_ma:
            return "PUT"
        return None

    async def get_expiry(self, candle: dict) -> int:
        return self.expiry_seconds