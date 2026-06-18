class RotationalStrategy:
    """
    Alternating strategy:
    - Trades on every 1‑minute candle.
    - Starts with PUT, then CALL, then PUT, then CALL, ...
    - Default expiry = 30 seconds (to allow martingale before next candle).
    """
    expiry_seconds = 30

    def __init__(self):
        self.trade_count = 0   # number of trades placed so far

    async def get_signal(self, candle: dict) -> str | None:
        self.trade_count += 1
        # Odd number -> PUT, even number -> CALL
        if self.trade_count % 2 == 1:
            return "PUT"
        else:
            return "CALL"

    async def get_expiry(self, candle: dict) -> int:
        return self.expiry_seconds
