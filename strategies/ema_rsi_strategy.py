"""
3 EMA (10, 50, 100) + RSI (14) Strategy
- CALL when price > EMA10 > EMA50 > EMA100 and RSI between 49 and 51
- PUT when price < EMA10 < EMA50 < EMA100 and RSI between 49 and 51
"""

class EMARSIStrategy:
    expiry_seconds = 60
    ema_periods = (10, 50, 100)
    rsi_period = 14
    rsi_low = 49
    rsi_high = 51

    def __init__(self):
        self.candle_history = []   # store close prices
        self.ema_values = {p: None for p in self.ema_periods}
        self.rsi = None

    def _calculate_ema(self, data, period):
        """Exponential Moving Average (pure Python, no numpy)"""
        if len(data) < period:
            return None
        alpha = 2 / (period + 1)
        ema = data[0]  # start with first value
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema

    def _calculate_rsi(self, data, period):
        """Relative Strength Index (pure Python)"""
        if len(data) < period + 1:
            return None
        deltas = []
        for i in range(1, len(data)):
            deltas.append(data[i] - data[i-1])
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    async def get_signal(self, candle):
        close = float(candle['close'])
        self.candle_history.append(close)

        # Keep only last 200 candles to save memory
        if len(self.candle_history) > 200:
            self.candle_history.pop(0)

        # Need enough data for the longest EMA (100) + RSI buffer
        if len(self.candle_history) < max(self.ema_periods) + self.rsi_period:
            return None

        # Calculate all EMAs
        for p in self.ema_periods:
            if len(self.candle_history) >= p:
                self.ema_values[p] = self._calculate_ema(self.candle_history[-p:], p)

        # Calculate RSI on last (rsi_period+1) candles
        if len(self.candle_history) >= self.rsi_period + 1:
            self.rsi = self._calculate_rsi(self.candle_history, self.rsi_period)
        else:
            return None

        price = close
        ema10 = self.ema_values[10]
        ema50 = self.ema_values[50]
        ema100 = self.ema_values[100]
        rsi = self.rsi

        # Debug output (optional)
        # print(f"[EMA_RSI] price={price:.5f} ema10={ema10:.5f} ema50={ema50:.5f} ema100={ema100:.5f} rsi={rsi:.2f}")

        # CALL condition
        if (price > ema10 > ema50 > ema100) and (self.rsi_low <= rsi <= self.rsi_high):
            return "CALL"

        # PUT condition
        if (price < ema10 < ema50 < ema100) and (self.rsi_low <= rsi <= self.rsi_high):
            return "PUT"

        return None

    async def get_expiry(self, candle):
        return self.expiry_seconds