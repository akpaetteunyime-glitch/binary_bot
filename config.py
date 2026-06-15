import os
from pathlib import Path


# -------------------- TELEGRAM --------------------
TELEGRAM_BOT_TOKEN = "your_TELEGRAM_BOT_TOKEN"
# -------------------- TRADING --------------------
# Get SSID from your broker's cookies (PocketOption example)
ACCOUNT_SSID = "your_pocket_option_ACCOUNT_SSID"
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

# Up to 50 preferred OTC assets (add/remove as needed)
PREFERRED_ASSETS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
    "NZDUSD_otc", "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc", "CHFJPY_otc",
    "AUDJPY_otc", "CADJPY_otc", "NZDJPY_otc", "EURCAD_otc", "GBPCAD_otc",
    "EURCHF_otc", "GBPCHF_otc", "AUDCHF_otc", "CADCHF_otc", "NZDCAD_otc",
    "USDCHF_otc", "USDNOK_otc", "USDSEK_otc", "USDDKK_otc", "USDZAR_otc",
    "EURTRY_otc", "GBPTRY_otc", "USDTRY_otc", "EURMXN_otc", "GBPMXN_otc",
    "USDMXN_otc", "USDPLN_otc", "EURHUF_otc", "GBPHUF_otc", "USDHUF_otc",
    "EURCZK_otc", "GBPCZK_otc", "USDCZK_otc", "USDILS_otc", "USDTHB_otc",
    "USDSGD_otc", "USDTWD_otc", "USDCNH_otc", "USDHKD_otc", "USDKRW_otc",
    "AUDNZD_otc", "EURNZD_otc", "GBPNZD_otc", "NZDCAD_otc", "CADNOK_otc"
]


SCAN_INTERVAL_SECONDS = 60   # how often to scan all assets for EMA+RSI condition