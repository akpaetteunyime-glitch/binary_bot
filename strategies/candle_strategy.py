class CandleColorStrategy:
    """
    Strategy: 
    - Previous candle RED (close < open) -> PUT at start of new candle
    - Previous candle GREEN (close > open) -> CALL at start of new candle
    """
    # Default expiry for this strategy (seconds)
    expiry_seconds = 60

    async def get_signal(self, candle: dict) -> str | None:
        open_price = float(candle['open'])
        close_price = float(candle['close'])
        if close_price < open_price:
            return "PUT"
        elif close_price > open_price:
            return "CALL"
        return None   # Doji – no trade

    async def get_expiry(self, candle: dict) -> int:
        """Return preferred expiry in seconds for the given candle."""
        return self.expiry_seconds