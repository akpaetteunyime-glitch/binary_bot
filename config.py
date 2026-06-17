import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()  # This loads variables from .env into os.environ

# -------------------- TELEGRAM --------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# -------------------- TRADING --------------------
ACCOUNT_SSID = os.getenv("ACCOUNT_SSID", "YOUR_ACCOUNT_SSID_HERE")
DATABASE_PATH = Path("data/users.db")

# Default trading settings
ASSET = "EURUSD_otc"
AMOUNT = 1.33
EXPIRY_SECONDS = 60
MARTINGALE_LEVELS = 4
MARTINGALE_MULTIPLIER = 2.2
MIN_PAYOUT = 83          # Legacy fallback

# -------------------- ASSET SCANNER --------------------
# Auto-switch to best asset based on payout + trend + smoothness
ASSET_SCANNER_ENABLED = True          # Master toggle
MIN_PAYOUT_TARGET = 92.0            # Only trade assets with ≥ this payout
PAYOUT_DROP_THRESHOLD = 85.0        # If current asset drops below this, force scan
MAX_WICK_RATIO = 0.25               # Max (wicks / range) for "smooth" candles
MIN_TREND_SCORE = 60.0              # Minimum trend strength (0-100)
SCANNER_CHECK_INTERVAL = 30         # Seconds between scanner checks
SCANNER_LOOKBACK_CANDLES = 20       # Candles to analyze for trend/wicks

# -------------------- ASSET CATEGORIES --------------------
# ONLY include assets verified to exist on PocketOption
# Remove any exotic/invalid pairs that cause "Assets not found" errors
ASSET_CATEGORIES = {
    "Forex OTC": [
        "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
        "NZDUSD_otc", "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc", "CHFJPY_otc",
        "AUDJPY_otc", "CADJPY_otc", "NZDJPY_otc", "EURCAD_otc", "GBPCAD_otc",
        "EURCHF_otc", "GBPCHF_otc", "AUDCHF_otc", "CADCHF_otc", "NZDCAD_otc",
        "USDCHF_otc", "AUDNZD_otc", "EURNZD_otc", "GBPNZD_otc", "AUDCAD_otc",
    ],
    "Forex Real": [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "CHFJPY",
        "AUDJPY", "CADJPY", "NZDJPY", "EURCAD", "GBPCAD",
        "EURCHF", "GBPCHF", "AUDCHF", "CADCHF", "NZDCAD",
        "USDCHF", "AUDNZD", "EURNZD", "GBPNZD", "AUDCAD",
    ],
    "Stocks OTC": [
        "AAPL_otc", "MSFT_otc", "GOOGL_otc", "AMZN_otc", "TSLA_otc",
        "NVDA_otc", "META_otc", "NFLX_otc", "BABA_otc", "INTC_otc",
        "AMD_otc", "BA_otc", "DIS_otc", "KO_otc", "PFE_otc",
        "JPM_otc", "V_otc", "WMT_otc", "JNJ_otc", "PG_otc",
    ],
    "Stocks Real": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
        "NVDA", "META", "NFLX", "BABA", "INTC",
        "AMD", "BA", "DIS", "KO", "PFE",
        "JPM", "V", "WMT", "JNJ", "PG",
    ],
    "Crypto OTC": [
        "BTCUSD_otc", "ETHUSD_otc", "LTCUSD_otc", "XRPUSD_otc", "ADAUSD_otc",
        "DOTUSD_otc", "DOGEUSD_otc", "BNBUSD_otc", "SOLUSD_otc", "MATICUSD_otc",
        "SHIBUSD_otc", "TRXUSD_otc", "AVAXUSD_otc", "UNIUSD_otc", "LINKUSD_otc",
    ],
    "Crypto Real": [
        "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "ADAUSD",
        "DOTUSD", "DOGEUSD", "BNBUSD", "SOLUSD", "MATICUSD",
        "SHIBUSD", "TRXUSD", "AVAXUSD", "UNIUSD", "LINKUSD",
    ],
    "Indices OTC": [
        "US30_otc", "US500_otc", "USTEC_otc", "GER30_otc", "UK100_otc",
        "FRA40_otc", "EUR50_otc", "JPN225_otc", "AUS200_otc", "NAS100_otc",
    ],
    "Indices Real": [
        "US30", "US500", "USTEC", "GER30", "UK100",
        "FRA40", "EUR50", "JPN225", "AUS200", "NAS100",
    ],
    "Commodities OTC": [
        "GOLD_otc", "SILVER_otc", "OIL_otc", "BRENT_otc", "NGAS_otc",
    ],
    "Commodities Real": [
        "GOLD", "SILVER", "OIL", "BRENT", "NGAS",
    ],
}

# Flattened list for the trading engine
PREFERRED_ASSETS = []
for cat_list in ASSET_CATEGORIES.values():
    PREFERRED_ASSETS.extend(cat_list)

SCAN_INTERVAL_SECONDS = 60  # Legacy EMARSI scanner interval (kept for compatibility)