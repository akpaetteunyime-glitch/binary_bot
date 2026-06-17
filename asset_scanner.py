"""
Asset Scanner Module - Simplified

1. Filter: payout >= min_payout_target
2. Rank by: highest trend + smoothest wicks (lowest wick ratio)
3. No hard thresholds on trend/wick/momentum
"""
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class AssetScore:
    asset: str
    payout: float
    trend_score: float       # 0-100
    wick_score: float        # 0-100 (higher = smoother)
    wick_ratio: float        # raw 0-1
    momentum_score: float    # 0-100
    overall_score: float
    trend_direction: str
    reason: str


class AssetScanner:
    def __init__(
        self,
        client,
        min_payout_target: float = 92.0,
        max_wick_ratio: float = 0.25,
        min_trend_score: float = 60.0,
        lookback_candles: int = 20,
        min_consecutive_candles: int = 3,
    ):
        self.client = client
        self.min_payout_target = min_payout_target
        self.max_wick_ratio = max_wick_ratio
        self.min_trend_score = min_trend_score
        self.lookback_candles = lookback_candles
        self.min_consecutive_candles = min_consecutive_candles
        self._valid_assets: set = set()
        self._invalid_assets: set = set()

    async def _get_payout_raw(self, asset: str) -> Optional[float]:
        try:
            result = await self.client.payout(asset)
            if result is None:
                return None
            if isinstance(result, dict):
                for key in ("payout", "profit", "percent", "value", "amount"):
                    if key in result and result[key] is not None:
                        try:
                            return float(result[key])
                        except (ValueError, TypeError):
                            continue
                return None
            if isinstance(result, str):
                try:
                    return float(result)
                except (ValueError, TypeError):
                    return None
            try:
                return float(result)
            except (ValueError, TypeError):
                return None
        except Exception:
            return None

    async def get_payout(self, asset: str) -> float:
        try:
            result = await self._get_payout_raw(asset)
            if result is not None:
                return result
            for method_name in ("get_payout", "check_payout", "get_profit", "profit"):
                if hasattr(self.client, method_name):
                    try:
                        method = getattr(self.client, method_name)
                        res = await method(asset)
                        if res is not None:
                            try:
                                return float(res)
                            except (ValueError, TypeError):
                                continue
                    except Exception:
                        pass
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _ema(prices: List[float], period: int) -> List[float]:
        if len(prices) < period:
            return prices[:]
        mult = 2.0 / (period + 1)
        ema_vals = [sum(prices[:period]) / period]
        for p in prices[period:]:
            ema_vals.append((p - ema_vals[-1]) * mult + ema_vals[-1])
        return ema_vals

    @staticmethod
    def _wick_ratio(candle: dict) -> float:
        o = float(candle.get("open", 0.0))
        c = float(candle.get("close", 0.0))
        h = candle.get("high")
        l = candle.get("low")
        if h is None or l is None:
            body = abs(c - o)
            est_high = max(o, c) + body * 0.1
            est_low = min(o, c) - body * 0.1
            h = float(h) if h is not None else est_high
            l = float(l) if l is not None else est_low
        else:
            h = float(h)
            l = float(l)
        range_ = h - l
        if range_ <= 0:
            return 0.0
        body = abs(c - o)
        wicks = range_ - body
        return max(0.0, wicks / range_)

    @staticmethod
    def _candle_direction(candle: dict) -> int:
        c = float(candle.get("close", 0.0))
        o = float(candle.get("open", 0.0))
        if c > o:
            return 1
        if c < o:
            return -1
        return 0

    def _analyze_trend(self, candles: List[dict]) -> Tuple[float, str]:
        if len(candles) < 10:
            return 0.0, "NONE"
        closes = [float(c["close"]) for c in candles if c.get("close") is not None]
        if len(closes) < 10:
            return 0.0, "NONE"
        p_fast = min(5, len(closes) // 2)
        p_mid = min(10, len(closes) // 2)
        p_slow = min(20, len(closes) // 2)
        if p_fast < 2:
            p_fast = 2
        if p_mid < 3:
            p_mid = 3
        if p_slow < 5:
            p_slow = 5
        ema_fast = self._ema(closes, p_fast)
        ema_mid = self._ema(closes, p_mid)
        ema_slow = self._ema(closes, p_slow)
        if len(ema_slow) < 2:
            return 0.0, "NONE"
        p = closes[-1]
        ef = ema_fast[-1] if len(ema_fast) > 0 else p
        em = ema_mid[-1] if len(ema_mid) > 0 else ef
        es = ema_slow[-1] if len(ema_slow) > 0 else em
        score = 0.0
        if ef > em > es:
            direction = "UP"
            score += 40
        elif ef < em < es:
            direction = "DOWN"
            score += 40
        else:
            direction = "NONE"
        if direction == "UP" and p > ef:
            score += 15
        elif direction == "DOWN" and p < ef:
            score += 15
        check_count = min(5, len(candles))
        recent_dirs = [self._candle_direction(c) for c in candles[-check_count:]]
        if direction == "UP":
            up_streak = sum(1 for d in recent_dirs if d == 1)
            score += (up_streak / check_count) * 25
        elif direction == "DOWN":
            down_streak = sum(1 for d in recent_dirs if d == -1)
            score += (down_streak / check_count) * 25
        slope_period = min(3, len(ema_mid) - 1)
        if slope_period >= 2 and ema_mid[-slope_period - 1] != 0:
            slope = (ema_mid[-1] - ema_mid[-slope_period - 1]) / ema_mid[-slope_period - 1] * 100
            score += min(abs(slope) * 2, 10)
        if direction == "UP" and len(candles) >= 5:
            highs = [float(c.get("high", max(float(c.get("open", 0)), float(c.get("close", 0))))) for c in candles[-5:]]
            if highs[-1] >= max(highs) * 0.99:
                score += 10
        elif direction == "DOWN" and len(candles) >= 5:
            lows = [float(c.get("low", min(float(c.get("open", 0)), float(c.get("close", 0))))) for c in candles[-5:]]
            if lows[-1] <= min(lows) * 1.01:
                score += 10
        final_score = min(score, 100)
        return final_score, direction

    def _analyze_wicks(self, candles: List[dict]) -> Tuple[float, float]:
        """Return (smoothness_score 0-100, avg_wick_ratio 0-1)."""
        if len(candles) < 5:
            return 50.0, 0.0
        sample = candles[-10:]
        scores = []
        raw_ratios = []
        for c in sample:
            wr = self._wick_ratio(c)
            raw_ratios.append(wr)
            s = max(0.0, (1.0 - wr / self.max_wick_ratio) * 100)
            scores.append(s)
        avg_score = sum(scores) / len(scores) if scores else 50.0
        avg_ratio = sum(raw_ratios) / len(raw_ratios) if raw_ratios else 0.0
        return avg_score, avg_ratio

    def _analyze_momentum(self, candles: List[dict], direction: str) -> float:
        if len(candles) < self.min_consecutive_candles:
            return 0.0
        check_len = min(self.min_consecutive_candles + 2, len(candles))
        dirs = [self._candle_direction(c) for c in candles[-check_len:]]
        if direction == "UP":
            match = sum(1 for d in dirs if d == 1)
        elif direction == "DOWN":
            match = sum(1 for d in dirs if d == -1)
        else:
            return 0.0
        return (match / len(dirs)) * 100

    async def score_asset(self, asset: str) -> Optional[AssetScore]:
        """Score asset. Only payout is a hard filter. Trend/wick/momentum are for ranking."""
        try:
            print(f"[SCANNER] Scoring {asset}...")
            payout = await self.get_payout(asset)
            print(f"[SCANNER] {asset} payout: {payout}%")
            if payout < self.min_payout_target:
                print(f"[SCANNER] {asset} REJECTED: payout {payout}% < {self.min_payout_target}%")
                return None

            candles = None
            try:
                candles = await asyncio.wait_for(self.client.history(asset, 60), timeout=10.0)
            except asyncio.TimeoutError:
                print(f"[SCANNER] {asset} history() timeout (10s)")
                return None
            except Exception as e:
                print(f"[SCANNER] history() failed for {asset}: {e}")

            if not candles or len(candles) < 10:
                print(f"[SCANNER] {asset} REJECTED: only {len(candles) if candles else 0} candles available")
                return None

            print(f"[SCANNER] {asset} candles: {len(candles)}")

            trend_score, direction = self._analyze_trend(candles)
            wick_score, wick_ratio = self._analyze_wicks(candles)
            momentum_score = self._analyze_momentum(candles, direction)

            # Ranking: payout 40%, trend 35%, wick_smoothness 15%, momentum 10%
            # Higher trend = better, lower wick_ratio = better
            overall = (
                (payout / 100.0) * 40
                + trend_score * 0.35
                + wick_score * 0.15
                + momentum_score * 0.10
            )

            reason = (
                f"Payout {payout:.0f}% | Trend {direction} {trend_score:.0f} | "
                f"Wicks {wick_score:.0f} (ratio {wick_ratio:.3f}) | Momentum {momentum_score:.0f}"
            )

            print(f"[SCANNER] {asset} ACCEPTED: overall={overall:.1f} | {reason}")

            return AssetScore(
                asset=asset,
                payout=payout,
                trend_score=trend_score,
                wick_score=wick_score,
                wick_ratio=wick_ratio,
                momentum_score=momentum_score,
                overall_score=overall,
                trend_direction=direction,
                reason=reason,
            )
        except Exception as e:
            print(f"[SCANNER] Error scoring {asset}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def find_best_asset(self, assets: List[str], current_asset: str = None) -> Optional[AssetScore]:
        """Scan all assets and return the best candidate.

        Only payout >= 92% is a hard filter.
        Everything else is used for ranking (highest trend, smoothest wicks wins).
        """
        scores = []
        checked = 0
        for asset in assets:
            if asset == current_asset:
                continue
            sc = await self.score_asset(asset)
            checked += 1
            if sc:
                scores.append(sc)
                print(f"[SCANNER] {checked}/{len(assets)-1} checked → {asset} ACCEPTED (score={sc.overall_score:.1f})")
        if not scores:
            print("[SCANNER] No assets passed payout filter")
            return None
        scores.sort(key=lambda x: x.overall_score, reverse=True)
        best = scores[0]
        print(f"[SCANNER] Best of {len(scores)} candidates: {best.asset} (score={best.overall_score:.1f})")
        return best

    async def check_current_asset(self, asset: str) -> Tuple[bool, float, float, float, float]:
        """Check current asset. Always returns full scores regardless of payout."""
        try:
            print(f"[SCANNER] Checking current asset {asset}...")

            payout = await self.get_payout(asset)
            print(f"[SCANNER] Current {asset} payout: {payout}%")

            candles = None
            try:
                candles = await asyncio.wait_for(self.client.history(asset, 60), timeout=10.0)
            except asyncio.TimeoutError:
                print(f"[SCANNER] Current {asset} history() timeout")
                if payout <= 0:
                    return False, 0.0, 0.0, 0.0, 0.0
                return False, payout, 0.0, 0.0, 0.0
            except Exception as e:
                print(f"[SCANNER] history() failed for current asset {asset}: {e}")

            if not candles or len(candles) < 10:
                print(f"[SCANNER] Current {asset} FAIL: insufficient candles ({len(candles) if candles else 0})")
                if payout <= 0:
                    return False, 0.0, 0.0, 0.0, 0.0
                return False, payout, 0.0, 0.0, 0.0

            print(f"[SCANNER] Current {asset} candles: {len(candles)}")

            trend_score, direction = self._analyze_trend(candles)
            wick_score, wick_ratio = self._analyze_wicks(candles)
            momentum_score = self._analyze_momentum(candles, direction)

            if payout <= 0:
                print(f"[SCANNER] Current {asset} FAIL: payout is 0 or None")
                return False, 0.0, trend_score, wick_score, momentum_score

            if payout < self.min_payout_target:
                print(f"[SCANNER] Current {asset} FAIL: payout {payout}% < {self.min_payout_target}%")
                return False, payout, trend_score, wick_score, momentum_score

            ok = payout >= self.min_payout_target

            status = "OK" if ok else "DEGRADED"
            print(f"[SCANNER] Current {asset} {status}: payout={payout:.0f}% trend={trend_score:.1f} wicks={wick_score:.1f} mom={momentum_score:.1f}")

            return ok, payout, trend_score, wick_score, momentum_score
        except Exception as e:
            print(f"[SCANNER] Error checking {asset}: {e}")
            import traceback
            traceback.print_exc()
            return False, 0.0, 0.0, 0.0, 0.0