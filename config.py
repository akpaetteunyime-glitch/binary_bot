import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()   # This loads variables from .env into os.environ


# -------------------- TELEGRAM --------------------
# TELEGRAM_BOT_TOKEN = "your_TELEGRAM_BOT_TOKEN"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
# -------------------- TRADING --------------------
# Get SSID from your broker's cookies (PocketOption example)
# ACCOUNT_SSID = "your_pocket_option_ACCOUNT_SSID"
ACCOUNT_SSID = os.getenv("ACCOUNT_SSID", "YOUR_ACCOUNT_SSID_HERE")
DATABASE_PATH = "bot_users.sqlite3"  # SQLite database for per-user broker sessions


#
# Database
DATABASE_PATH = Path("data/users.db")

# Default trading settings
ASSET = "EURUSD_otc"
AMOUNT = 1.33
EXPIRY_SECONDS = 60
MARTINGALE_LEVELS = 4
MARTINGALE_MULTIPLIER = 2.2
MIN_PAYOUT = 83               # Legacy minimum payout (fallback)

# NEW: Auto-switch settings
MIN_PAYOUT_TARGET = 92        # Desired minimum payout percentage
RANGING_THRESHOLD = 0.005     # Max (high-low)/mean to consider ranging (0.5%)
SCAN_INTERVAL_MINUTES = 5     # How often to scan all assets in background

## ----- ASSET CATEGORIES (for Telegram menu) -----
ASSET_CATEGORIES = {
    "Forex OTC": [
        "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
        "NZDUSD_otc", "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc", "CHFJPY_otc",
        "AUDJPY_otc", "CADJPY_otc", "NZDJPY_otc", "EURCAD_otc", "GBPCAD_otc",
        "EURCHF_otc", "GBPCHF_otc", "AUDCHF_otc", "CADCHF_otc", "NZDCAD_otc",
        "USDCHF_otc", "USDNOK_otc", "USDSEK_otc", "USDDKK_otc", "USDZAR_otc",
        "EURTRY_otc", "GBPTRY_otc", "USDTRY_otc", "EURMXN_otc", "GBPMXN_otc",
        "USDMXN_otc", "USDPLN_otc", "EURHUF_otc", "GBPHUF_otc", "USDHUF_otc",
        "EURCZK_otc", "GBPCZK_otc", "USDCZK_otc", "USDILS_otc", "USDTHB_otc",
        "USDSGD_otc", "USDTWD_otc", "USDCNH_otc", "USDHKD_otc", "USDKRW_otc",
        "AUDNZD_otc", "EURNZD_otc", "GBPNZD_otc", "NZDCAD_otc", "CADNOK_otc",
        "EURSEK_otc", "GBPNOK_otc", "AUDCAD_otc", "EURZAR_otc", "USDINR_otc",
        "USDMYR_otc", "USDPHP_otc", "USDRUB_otc", "USDBRL_otc", "USDCLP_otc",
        "AEDCNY_otc", "MADUSD_otc", "BHDCNY_otc", "NGNUSD_otc", "SARCNY_otc "
    ],
    "Forex Real": [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "CHFJPY",
        "AUDJPY", "CADJPY", "NZDJPY", "EURCAD", "GBPCAD",
        "EURCHF", "GBPCHF", "AUDCHF", "CADCHF", "NZDCAD",
        "USDCHF", "USDNOK", "USDSEK", "USDDKK", "USDZAR",
        "EURTRY", "GBPTRY", "USDTRY", "EURMXN", "GBPMXN",
        "USDMXN", "USDPLN", "EURHUF", "GBPHUF", "USDHUF",
        "EURCZK", "GBPCZK", "USDCZK", "USDILS", "USDTHB",
        "USDSGD", "USDTWD", "USDCNH", "USDHKD", "USDKRW",
        "AUDNZD", "EURNZD", "GBPNZD", "NZDCAD", "CADNOK",
        "EURSEK", "GBPNOK", "AUDCAD", "EURZAR", "USDINR",
        "USDMYR", "USDPHP", "USDRUB", "USDBRL", "USDCLP"
    ],
    "Stocks OTC": [
        "AAPL_otc", "MSFT_otc", "GOOGL_otc", "AMZN_otc", "TSLA_otc",
        "NVDA_otc", "META_otc", "NFLX_otc", "BABA_otc", "INTC_otc",
        "AMD_otc", "BA_otc", "DIS_otc", "KO_otc", "PFE_otc",
        "JPM_otc", "V_otc", "WMT_otc", "JNJ_otc", "PG_otc"
    ],
    "Stocks Real": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
        "NVDA", "META", "NFLX", "BABA", "INTC",
        "AMD", "BA", "DIS", "KO", "PFE",
        "JPM", "V", "WMT", "JNJ", "PG"
    ],
    "Crypto OTC": [
        "BTCUSD_otc", "ETHUSD_otc", "LTCUSD_otc", "XRPUSD_otc", "ADAUSD_otc",
        "DOTUSD_otc", "DOGEUSD_otc", "BNBUSD_otc", "SOLUSD_otc", "MATICUSD_otc",
        "SHIBUSD_otc", "TRXUSD_otc", "AVAXUSD_otc", "UNIUSD_otc", "LINKUSD_otc"
    ],
    "Crypto Real": [
        "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "ADAUSD",
        "DOTUSD", "DOGEUSD", "BNBUSD", "SOLUSD", "MATICUSD",
        "SHIBUSD", "TRXUSD", "AVAXUSD", "UNIUSD", "LINKUSD"
    ],
    "Indices OTC": [
        "US30_otc", "US500_otc", "USTEC_otc", "GER30_otc", "UK100_otc",
        "FRA40_otc", "EUR50_otc", "JPN225_otc", "AUS200_otc", "CHN50_otc",
        "HK50_otc", "INDIA50_otc", "NAS100_otc", "SPX500_otc", "DAX30_otc"
    ],
    "Indices Real": [
        "US30", "US500", "USTEC", "GER30", "UK100",
        "FRA40", "EUR50", "JPN225", "AUS200", "CHN50",
        "HK50", "INDIA50", "NAS100", "SPX500", "DAX30"
    ]
}

# ----- Flattened list for the trading engine (all assets) -----
PREFERRED_ASSETS = []
for cat_list in ASSET_CATEGORIES.values():
    PREFERRED_ASSETS.extend(cat_list)

SCAN_INTERVAL_SECONDS = 60   # how often to scan all assets for EMA+RSI condition