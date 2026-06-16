from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ASSET_CATEGORIES

session_manager = None

def _parse_manual_config(text: str) -> dict:
    config = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key in {"amount", "expiry_seconds", "martingale_levels", "martingale_multiplier", "asset", "account_ssid", "ssid", "min_payout", "preferred_assets"}:
            config[key] = value
    if "ssid" in config and "account_ssid" not in config:
        config["account_ssid"] = config.pop("ssid")
    if "amount" in config:
        config["amount"] = float(config["amount"])
    if "expiry_seconds" in config:
        config["expiry_seconds"] = int(config["expiry_seconds"])
    if "martingale_levels" in config:
        config["martingale_levels"] = int(config["martingale_levels"])
    if "martingale_multiplier" in config:
        config["martingale_multiplier"] = float(config["martingale_multiplier"])
    if "min_payout" in config:
        config["min_payout"] = int(config["min_payout"])
    if "preferred_assets" in config:
        config["preferred_assets"] = [a.strip() for a in value.replace(" ", ",").split(",") if a.strip()]
    return config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🟢 AUTO TRADING ON", callback_data="auto_on")],
        [InlineKeyboardButton("🔴 AUTO TRADING OFF", callback_data="auto_off")],
        [InlineKeyboardButton("⚙️ MARTINGALE TOGGLE", callback_data="martingale_toggle")],
        [InlineKeyboardButton("🛑 MARTINGALE OFF", callback_data="martingale_off")],
        [InlineKeyboardButton("4 LVL / 2.2x", callback_data="preset_4_22"), InlineKeyboardButton("6 LVL / 2.5x", callback_data="preset_6_25")],
        [InlineKeyboardButton("💰 SET AMOUNT", callback_data="set_amount")],
        [InlineKeyboardButton("⏱️ SET EXPIRY", callback_data="set_expiry")],
        [InlineKeyboardButton("🎲 CHANGE STRATEGY", callback_data="change_strategy")],
        [InlineKeyboardButton("📅 SET SESSIONS", callback_data="set_sessions")],
        [InlineKeyboardButton("🔐 LINK MY SSID", callback_data="link_ssid")],
        [InlineKeyboardButton("📝 MANUAL CONFIG", callback_data="manual_config")],
        [InlineKeyboardButton("🔄 CHANGE ASSET", callback_data="change_asset")],
        [InlineKeyboardButton("📊 Balance", callback_data="balance")],
        [InlineKeyboardButton("🟢 Force CALL", callback_data="force_call")],
        [InlineKeyboardButton("🔴 Force PUT", callback_data="force_put")],
        [InlineKeyboardButton("📈 Status", callback_data="status")],
    ]
    await update.message.reply_text(
        "🤖 *Binary Bot Control Panel*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global session_manager
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_id = user.id if user else None
    username = user.username if user else None

    if not session_manager:
        await query.edit_message_text("Session manager not ready.")
        return

    # ----- Asset selection (from category drill-down) -----
    if data.startswith("asset_"):
        asset = data[6:]
        try:
            success = await session_manager.set_asset(user_id, username, asset)
            if success:
                await query.edit_message_text(f"✅ Asset changed to *{asset}*", parse_mode="Markdown")
            else:
                await query.edit_message_text(f"❌ Failed to change asset")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
        return

    # ----- Category selection -----
    if data.startswith("cat_"):
        category = data[4:]
        assets = ASSET_CATEGORIES.get(category, [])
        if not assets:
            await query.edit_message_text("No assets in this category.")
            return
        rows = []
        row = []
        for asset in assets:
            row.append(InlineKeyboardButton(asset, callback_data=f"asset_{asset}"))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("🔙 Categories", callback_data="change_asset")])
        rows.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")])
        await query.edit_message_text(
            f"📊 *{category} – select asset*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    # ----- Amount selection -----
    if data.startswith("amount_"):
        val = data[7:]
        if val == "custom":
            context.user_data["awaiting_input"] = "custom_amount"
            await query.edit_message_text("Send the new base amount (e.g., 5.5):")
            return
        else:
            amount = float(val)
            try:
                success = await session_manager.set_amount(user_id, username, amount)
                if success:
                    await query.edit_message_text(f"✅ Base amount set to ${amount:.2f}")
                else:
                    await query.edit_message_text("❌ Failed to set amount")
            except Exception as e:
                await query.edit_message_text(f"Error: {e}")
        return

    # ----- Expiry selection -----
    if data == "set_expiry":
        keyboard = [
            [InlineKeyboardButton("15s", callback_data="expiry_15"),
             InlineKeyboardButton("30s", callback_data="expiry_30"),
             InlineKeyboardButton("60s", callback_data="expiry_60")],
            [InlineKeyboardButton("120s", callback_data="expiry_120"),
             InlineKeyboardButton("300s", callback_data="expiry_300"),
             InlineKeyboardButton("✏️ Custom", callback_data="expiry_custom")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")],
        ]
        await query.edit_message_text(
            "⏱️ *Select trade expiry time*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if data.startswith("expiry_"):
        val = data[7:]
        if val == "custom":
            context.user_data["awaiting_input"] = "custom_expiry"
            await query.edit_message_text("Send the new expiry time in seconds (e.g., 45):")
            return
        else:
            expiry = int(val)
            try:
                success = await session_manager.set_expiry(user_id, username, expiry)
                if success:
                    await query.edit_message_text(f"✅ Expiry set to {expiry}s")
                else:
                    await query.edit_message_text("❌ Failed to set expiry")
            except Exception as e:
                await query.edit_message_text(f"Error: {e}")
        return

    # ----- Strategy selection -----
    if data == "change_strategy":
        keyboard = [
            [InlineKeyboardButton("🌈 Candle Color", callback_data="strategy_CandleColor")],
            [InlineKeyboardButton("📈 MA Crossover", callback_data="strategy_MACrossover")],
            [InlineKeyboardButton("⏰ Time Stat Arbitrage", callback_data="strategy_TimeStatArbitrage")],
            [InlineKeyboardButton("📊 3 EMA + RSI", callback_data="strategy_EMARSI")],
            [InlineKeyboardButton("🔄 Rotational", callback_data="strategy_Rotational")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")],
        ]
        await query.edit_message_text(
            "🎲 *Select trading strategy*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if data.startswith("strategy_"):
        strat = data[9:]
        try:
            success = await session_manager.set_strategy(user_id, username, strat)
            if success:
                await query.edit_message_text(f"✅ Strategy changed to *{strat}*", parse_mode="Markdown")
            else:
                await query.edit_message_text(f"❌ Failed to change strategy")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
        return

    # ----- Change Asset (show categories) -----
    if data == "change_asset":
        rows = []
        row = []
        for category in ASSET_CATEGORIES.keys():
            row.append(InlineKeyboardButton(category, callback_data=f"cat_{category}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")])
        await query.edit_message_text(
            "📊 *Select asset category*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    # ----- Session scheduling -----
    if data == "set_sessions":
        keyboard = [
            [InlineKeyboardButton("🔘 ENABLE SESSIONS", callback_data="sessions_enable")],
            [InlineKeyboardButton("🔴 DISABLE SESSIONS", callback_data="sessions_disable")],
            [InlineKeyboardButton("📊 Sessions per day", callback_data="sessions_per_day")],
            [InlineKeyboardButton("🕒 Start hour", callback_data="session_start_hour")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")],
        ]
        await query.edit_message_text(
            "📅 *Session Scheduling Settings*\n"
            "Set number of sessions per day, trades per session, and start hour.\n"
            "Sessions: 3 (gap 5h), 5 (gap 3h), 15 (gap 1h).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "sessions_enable":
        await session_manager.set_sessions_enabled(user_id, username, True)
        await query.edit_message_text("✅ Session scheduling ENABLED")
        return
    if data == "sessions_disable":
        await session_manager.set_sessions_enabled(user_id, username, False)
        await query.edit_message_text("✅ Session scheduling DISABLED")
        return

    if data == "sessions_per_day":
        keyboard = [
            [InlineKeyboardButton("3 sessions (8,9,10 wins)", callback_data="sess_preset_3")],
            [InlineKeyboardButton("5 sessions (4,5,6 wins)", callback_data="sess_preset_5")],
            [InlineKeyboardButton("15 sessions (1,2,3 wins)", callback_data="sess_preset_15")],
            [InlineKeyboardButton("🔙 Back", callback_data="set_sessions")],
        ]
        await query.edit_message_text("Select sessions per day:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("sess_preset_"):
        val = data[12:]  # '3', '5', '15'
        sessions = int(val)
        if sessions == 3:
            choices = [8,9,10]
        elif sessions == 5:
            choices = [4,5,6]
        elif sessions == 15:
            choices = [1,2,3]
        else:
            await query.edit_message_text("Invalid selection")
            return
        keyboard = []
        for t in choices:
            keyboard.append([InlineKeyboardButton(f"{t} wins/session", callback_data=f"sess_set_{sessions}_{t}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="sessions_per_day")])
        await query.edit_message_text(f"Select trades per session for {sessions} sessions/day:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("sess_set_"):
        parts = data[9:].split('_')
        sessions = int(parts[0])
        trades = int(parts[1])
        await session_manager.set_session_schedule(user_id, username, sessions_per_day=sessions, trades_per_session=trades)
        await query.edit_message_text(f"✅ Sessions per day: {sessions}, trades per session: {trades}")
        return

    if data == "session_start_hour":
        rows = []
        row = []
        for h in range(24):
            row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"sess_hour_{h}"))
            if len(row) == 6:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="set_sessions")])
        await query.edit_message_text("Select session start hour (24h format):", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("sess_hour_"):
        hour = int(data[10:])
        await session_manager.set_session_schedule(user_id, username, start_hour=hour)
        await query.edit_message_text(f"✅ Session start hour set to {hour:02d}:00")
        return

    # ----- Back to main menu -----
    if data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🟢 AUTO TRADING ON", callback_data="auto_on")],
            [InlineKeyboardButton("🔴 AUTO TRADING OFF", callback_data="auto_off")],
            [InlineKeyboardButton("⚙️ MARTINGALE TOGGLE", callback_data="martingale_toggle")],
            [InlineKeyboardButton("🛑 MARTINGALE OFF", callback_data="martingale_off")],
            [InlineKeyboardButton("4 LVL / 2.2x", callback_data="preset_4_22"), InlineKeyboardButton("6 LVL / 2.5x", callback_data="preset_6_25")],
            [InlineKeyboardButton("💰 SET AMOUNT", callback_data="set_amount")],
            [InlineKeyboardButton("⏱️ SET EXPIRY", callback_data="set_expiry")],
            [InlineKeyboardButton("🎲 CHANGE STRATEGY", callback_data="change_strategy")],
            [InlineKeyboardButton("📅 SET SESSIONS", callback_data="set_sessions")],
            [InlineKeyboardButton("🔐 LINK MY SSID", callback_data="link_ssid")],
            [InlineKeyboardButton("📝 MANUAL CONFIG", callback_data="manual_config")],
            [InlineKeyboardButton("🔄 CHANGE ASSET", callback_data="change_asset")],
            [InlineKeyboardButton("📊 Balance", callback_data="balance")],
            [InlineKeyboardButton("🟢 Force CALL", callback_data="force_call")],
            [InlineKeyboardButton("🔴 Force PUT", callback_data="force_put")],
            [InlineKeyboardButton("📈 Status", callback_data="status")],
        ]
        await query.edit_message_text(
            "🤖 *Binary Bot Control Panel*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ----- Set amount menu -----
    if data == "set_amount":
        keyboard = [
            [InlineKeyboardButton("$1", callback_data="amount_1"),
             InlineKeyboardButton("$2", callback_data="amount_2"),
             InlineKeyboardButton("$3", callback_data="amount_3")],
            [InlineKeyboardButton("$5", callback_data="amount_5"),
             InlineKeyboardButton("$10", callback_data="amount_10"),
             InlineKeyboardButton("$20", callback_data="amount_20")],
            [InlineKeyboardButton("✏️ Custom", callback_data="amount_custom")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")],
        ]
        await query.edit_message_text(
            "💰 *Select base trade amount*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ----- Existing handlers (auto_on, auto_off, martingale, presets, etc.) -----
    if data == "auto_on":
        try:
            await session_manager.start_auto_trading(user_id, username)
            await query.edit_message_text("✅ *Auto trading ENABLED*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"Could not enable: {e}")
    elif data == "auto_off":
        await session_manager.stop_auto_trading(user_id)
        await query.edit_message_text("⏹️ *Auto trading DISABLED*", parse_mode="Markdown")
    elif data == "martingale_toggle":
        enabled = await session_manager.toggle_martingale(user_id, username)
        state = "ENABLED" if enabled else "DISABLED"
        await query.edit_message_text(f"⚙️ *Martingale {state}*", parse_mode="Markdown")
    elif data == "martingale_off":
        await session_manager.disable_martingale(user_id, username)
        await query.edit_message_text("🛑 *Martingale DISABLED and reset*", parse_mode="Markdown")
    elif data == "preset_4_22":
        await session_manager.set_martingale_settings(user_id, username, levels=4, multiplier=2.2)
        await session_manager.enable_martingale(user_id, username)
        await query.edit_message_text("⚙️ *Martingale preset applied: 4 levels, 2.2x*", parse_mode="Markdown")
    elif data == "preset_6_25":
        await session_manager.set_martingale_settings(user_id, username, levels=6, multiplier=2.5)
        await session_manager.enable_martingale(user_id, username)
        await query.edit_message_text("⚙️ *Martingale preset applied: 6 levels, 2.5x*", parse_mode="Markdown")
    elif data == "link_ssid":
        context.user_data["awaiting_input"] = "ssid"
        await query.edit_message_text(
            "🔐 Send your PocketOption SSID only.\nExample: 42[\"auth\",{\"session\":\"...\"}]\nUse /cancelconfig to stop."
        )
    elif data == "manual_config":
        context.user_data["awaiting_input"] = "config"
        await query.edit_message_text(
            "📝 Send config lines:\nAMOUNT=1.33\nEXPIRY_SECONDS=60\nMARTINGALE_LEVELS=4\nMARTINGALE_MULTIPLIER=2.2\nASSET=GBPUSD_otc\nMIN_PAYOUT=83\nPREFERRED_ASSETS=EURUSD_otc,GBPUSD_otc\nSSID=your_ssid\nUse /cancelconfig to stop."
        )
    elif data == "balance":
        try:
            bal = await session_manager.get_balance(user_id)
            await query.edit_message_text(f"💰 *Balance:* ${bal:.2f}", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
    elif data == "force_call":
        try:
            await session_manager.place_trade(user_id, "CALL", manual=True)
            await query.edit_message_text("🟢 *Manual CALL placed*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
    elif data == "force_put":
        try:
            await session_manager.place_trade(user_id, "PUT", manual=True)
            await query.edit_message_text("🔴 *Manual PUT placed*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
    elif data == "status":
        status = await session_manager.get_status(user_id)
        text = (
            f"*Auto Trading:* {'🟢 ON' if status['auto_trading'] else '🔴 OFF'}\n"
            f"*Trades Today:* {status['trades_today']}\n"
            f"*{status['martingale']}*\n"
            f"*Asset:* {status['asset']}\n"
            f"*Base Amount:* ${status['base_amount']:.2f}\n"
            f"*Default Expiry:* {status['default_expiry']}s\n"
            f"*Daily Loss:* ${status['daily_loss']:.2f}\n"
            f"*Strategy:* {status['strategy']}\n"
            f"*Sessions:* {'Enabled' if status['sessions_enabled'] else 'Disabled'}\n"
            f"*Sessions/day:* {status['sessions_per_day']}\n"
            f"*Trades/session:* {status['trades_per_session']}\n"
            f"*Start hour:* {status['session_start_hour']:02d}:00\n"
            f"*Session wins:* {status['session_wins']}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")

# ----- Command handlers (unchanged) -----
async def martingale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    enabled = await session_manager.toggle_martingale(update.effective_user.id, update.effective_user.username)
    state = "enabled" if enabled else "disabled"
    await update.message.reply_text(f"⚙️ Martingale {state}.")

async def set_martingale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setmartingale <levels> [multiplier]")
        return
    try:
        levels = int(context.args[0])
        multiplier = float(context.args[1]) if len(context.args) > 1 else None
        await session_manager.set_martingale_settings(update.effective_user.id, update.effective_user.username, levels=levels, multiplier=multiplier)
        await update.message.reply_text(f"⚙️ Martingale updated: levels={levels}, multiplier={multiplier if multiplier else 'unchanged'}")
    except ValueError as e:
        await update.message.reply_text(f"Invalid: {e}")

async def set_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setpayout <percentage>")
        return
    try:
        payout = int(context.args[0])
        await session_manager.set_min_payout(update.effective_user.id, update.effective_user.username, min_payout=payout)
        await update.message.reply_text(f"✅ Minimum payout set to {payout}%")
    except ValueError as e:
        await update.message.reply_text(f"Invalid: {e}")

async def set_asset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setasset ASSET\nExample: /setasset GBPUSD_otc")
        return
    new_asset = context.args[0].strip()
    try:
        success = await session_manager.set_asset(update.effective_user.id, update.effective_user.username, new_asset)
        if success:
            await update.message.reply_text(f"✅ Asset changed to {new_asset}")
        else:
            await update.message.reply_text("❌ Failed.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_input", None)
    await update.message.reply_text("Cancelled.")

async def manual_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("awaiting_input")
    if not mode:
        return
    text = (update.message.text or "").strip()
    if text.lower() in {"cancel", "/cancelconfig"}:
        context.user_data.pop("awaiting_input", None)
        await update.message.reply_text("Cancelled.")
        return
    try:
        user = update.effective_user
        if mode == "ssid":
            await session_manager.link_ssid(user.id, user.username, text)
            context.user_data.pop("awaiting_input", None)
            await update.message.reply_text("✅ SSID saved.")
            return
        if mode == "custom_amount":
            amount = float(text)
            success = await session_manager.set_amount(user.id, user.username, amount)
            context.user_data.pop("awaiting_input", None)
            if success:
                await update.message.reply_text(f"✅ Base amount set to ${amount:.2f}")
            else:
                await update.message.reply_text("❌ Failed to set amount")
            return
        if mode == "custom_expiry":
            expiry = int(text)
            success = await session_manager.set_expiry(user.id, user.username, expiry)
            context.user_data.pop("awaiting_input", None)
            if success:
                await update.message.reply_text(f"✅ Expiry set to {expiry}s")
            else:
                await update.message.reply_text("❌ Failed to set expiry")
            return
        parsed = _parse_manual_config(text)
        if not parsed:
            await update.message.reply_text("No valid keys found.")
            return
        await session_manager.update_user_config(user.id, user.username, parsed)
        context.user_data.pop("awaiting_input", None)
        await update.message.reply_text("✅ Config updated.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Telegram error: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("An unexpected error occurred. Try again.")
        except Exception:
            pass