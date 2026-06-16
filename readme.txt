================================================================================
         🤖 BINARY OPTIONS TRADING BOT – Telegram Edition
================================================================================

An advanced, multi‑strategy Telegram trading bot for PocketOption.
Supports martingale, real‑time asset scanning, session limits, and visual 
trade notifications. Built with Python 3.10+, python-telegram-bot, 
BinaryOptionsToolsV2, and asyncio.

================================================================================
✨ FEATURES
================================================================================

  • 📈 Multiple trading strategies – switch on the fly:
       - Candle Color        (CALL on green, PUT on red)
       - MA Crossover        (2 & 5 period moving averages)
       - Time‑Based Stat Arb (learns win rates per minute over 30 days)
       - 3 EMA + RSI         (10,50,100 EMAs + RSI 49‑51)
       - Rotational          (alternates PUT/CALL every minute, expiry 59s)

  • 🎯 Martingale system
       - Configurable levels and multiplier (e.g., 4 levels × 2.2)
       - Automatically resets on a win; persists on asset switches

  • 🔄 Auto‑asset switching (for EMARSI strategy)
       - Scans all preferred assets every 60 seconds
       - Switches to one meeting the 3 EMA + RSI condition

  • 💱 100+ assets (Forex, Stocks, Crypto, Indices)
       - Organised into categories via Telegram buttons
       - Supports both OTC and real symbols

  • 💰 Trade amount & expiry
       - Preset buttons: $1, $2, $3, $5, $10, $20 + custom
       - Expiry presets: 15s, 30s, 60s, 120s, 300s + custom

  • 🖼️ Visual trade notifications
       - Sends up.jpg, down.jpg, win.jpg with captions
       - Losses never appear in Telegram

  • 👥 Multi‑user support
       - Each Telegram user has an isolated session, SSID, and settings
       - All trade logs are private to each user

  • ⏰ Daily session limits
       - 5 sessions per day, each with 8 winning trades
       - Martingale steps are not counted

  • 📦 Persistent storage
       - SQLite database with encrypted SSIDs

  • 🚀 Ready for VPS
       - Includes systemd service configuration for 24/7 operation

================================================================================
📋 PREREQUISITES
================================================================================

  • Python 3.10+ (3.11 or 3.12 recommended)
  • A Telegram Bot Token from @BotFather
  • A PocketOption account (demo or live)
  • Your PocketOption SSID (see "How to get your SSID" below)
  • (Optional) up.jpg, down.jpg, win.jpg for visual notifications

================================================================================
🛠️ INSTALLATION
================================================================================

1. Clone the repository:
   git clone https://github.com/yourusername/binary-bot.git
   cd binary-bot

2. Create a virtual environment:
   python3 -m venv venv
   source venv/bin/activate          (Windows: venv\Scripts\activate)

3. Install dependencies:
   pip install -r requirements.txt

4. Set up the bot token:
   Create a .env file in the project root:
   echo "TELEGRAM_BOT_TOKEN=your_bot_token_here" > .env

   Or export it directly:
   export TELEGRAM_BOT_TOKEN=your_bot_token_here

5. (Optional) Add visual images:
   Place up.jpg, down.jpg, win.jpg in the same folder as main.py.

================================================================================
⚙️ CONFIGURATION
================================================================================

All settings are in config.py. Key variables:

  TELEGRAM_BOT_TOKEN      # Your bot token (loaded from .env)
  ASSET                   # Default trading asset (e.g., EURUSD_otc)
  AMOUNT                  # Base trade amount in USD
  EXPIRY_SECONDS          # Default expiry (60s)
  MARTINGALE_LEVELS       # Number of martingale steps
  MARTINGALE_MULTIPLIER   # Stake multiplier per loss
  PREFERRED_ASSETS        # List of assets to scan/display
  ASSET_CATEGORIES        # Grouped assets for the Telegram menu

You can modify these directly or use the Telegram commands to change them on the fly.

================================================================================
▶️ RUNNING THE BOT
================================================================================

Locally (development):
  python main.py

On a VPS with systemd (production):
  1. Create a service file at /etc/systemd/system/binary_bot.service:
     [Unit]
     Description=Binary Trading Bot
     After=network.target

     [Service]
     Type=simple
     User=your-username
     WorkingDirectory=/home/your-username/binary-bot
     Environment="PATH=/home/your-username/binary-bot/venv/bin"
     ExecStart=/home/your-username/binary-bot/venv/bin/python /home/your-username/binary-bot/main.py
     Restart=always
     RestartSec=10

     [Install]
     WantedBy=multi-user.target

  2. Enable and start:
     sudo systemctl daemon-reload
     sudo systemctl enable binary_bot
     sudo systemctl start binary_bot

  3. Check logs:
     sudo journalctl -u binary_bot -f

================================================================================
📲 TELEGRAM BOT USAGE
================================================================================

Start a chat with your bot and send /start. You'll see the main control panel:

  🤖 Binary Bot Control Panel

  🟢 AUTO TRADING ON
  🔴 AUTO TRADING OFF
  ⚙️ MARTINGALE TOGGLE
  🛑 MARTINGALE OFF
  4 LVL / 2.2x    6 LVL / 2.5x
  💰 SET AMOUNT
  ⏱️ SET EXPIRY
  🎲 CHANGE STRATEGY
  🔐 LINK MY SSID
  📝 MANUAL CONFIG
  🔄 CHANGE ASSET
  📊 Balance
  🟢 Force CALL
  🔴 Force PUT
  📈 Status

  • LINK MY SSID – send your PocketOption SSID (only once).
  • AUTO TRADING ON/OFF – enables/disables automated trading.
  • CHANGE STRATEGY – pick one of the 5 strategies.
  • CHANGE ASSET – choose from categories (Forex OTC, Stocks Real, Crypto, etc.).
  • SET AMOUNT – set base trade amount (presets + custom).
  • SET EXPIRY – set trade expiry (presets + custom).
  • MARTINGALE TOGGLE/OFF – enable/disable martingale.
  • PRESETS – quick martingale setups.
  • Force CALL/PUT – place a manual trade.
  • Balance / Status – view account balance and current settings.

================================================================================
🧠 HOW THE STRATEGIES WORK
================================================================================

  Strategy                 Description
  ----------------------------------------------------------------
  Candle Color             CALL on green candle, PUT on red.
  MA Crossover             2‑period and 5‑period MA crossover.
  Time Stat Arbitrage      Learns win rate per minute over 30 days;
                           trades only if win rate ≥ 55% and ≥5 trades.
  3 EMA + RSI              Price > EMA10 > EMA50 > EMA100 and RSI 49‑51 → CALL;
                           reverse for PUT.
  Rotational               Alternates PUT/CALL every minute (starts with PUT);
                           default expiry 59s.

================================================================================
🔒 HOW TO GET YOUR POCKETOPTION SSID
================================================================================

  1. Open PocketOption in your browser and log in.
  2. Open Developer Tools (F12) → Application → Storage → Cookies.
  3. Look for a cookie named "ssid" (or "session").
  4. Copy its value (it starts with 42["auth",{...}]).
  5. Send this value to the bot via the LINK MY SSID button.

================================================================================
🗃️ PROJECT STRUCTURE
================================================================================

  binary-bot/
  ├── main.py                 # Entry point
  ├── config.py               # Configuration & asset list
  ├── database.py             # SQLite user management
  ├── ssid_crypto.py          # Encryption for SSIDs
  ├── session_manager.py      # User sessions & candle streaming
  ├── trading_engine.py       # Core trading logic & strategies
  ├── telegram_bot.py         # Telegram handlers & UI
  ├── strategies/             # Strategy implementations
  │   ├── candle_strategy.py
  │   ├── ma_crossover_strategy.py
  │   ├── time_stat_arbitrage.py
  │   ├── ema_rsi_strategy.py
  │   └── rotational_strategy.py
  ├── data/                   # SQLite database & encryption key
  ├── up.jpg / down.jpg / win.jpg   # Optional visual images
  ├── requirements.txt
  └── README.md / README.txt

================================================================================
🤝 CONTRIBUTING
================================================================================

Contributions are welcome! If you have a new strategy, a bug fix, or an improvement:

  1. Fork the repository.
  2. Create a new branch (git checkout -b feature/amazing-strategy).
  3. Make your changes.
  4. Commit and push.
  5. Open a Pull Request.

Please ensure your code follows PEP8 and includes appropriate comments.

================================================================================
📜 LICENSE
================================================================================

This project is licensed under the MIT License – see the LICENSE file for details.

================================================================================
⚠️ DISCLAIMER
================================================================================

This bot is for educational purposes only. Binary options trading carries 
substantial risk of loss. The author is not responsible for any financial 
losses incurred using this software. Always test on a demo account first.

================================================================================
📬 SUPPORT & FEEDBACK
================================================================================

For questions or suggestions, open an issue on GitHub or reach out via Telegram.

Happy Trading! 🚀