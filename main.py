import asyncio
from pathlib import Path
import telegram_bot
from session_manager import SessionManager
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import InputFile
from config import TELEGRAM_BOT_TOKEN

async def main():
    session_manager = SessionManager()
    telegram_bot.session_manager = session_manager

    tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", telegram_bot.start))
    tg_app.add_handler(CommandHandler("martingale", telegram_bot.martingale))
    tg_app.add_handler(CommandHandler("setmartingale", telegram_bot.set_martingale))
    tg_app.add_handler(CommandHandler("setpayout", telegram_bot.set_payout))
    tg_app.add_handler(CommandHandler("setasset", telegram_bot.set_asset_command))
    tg_app.add_handler(CommandHandler("cancelconfig", telegram_bot.cancel_config))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_bot.manual_config_input))
    tg_app.add_handler(CallbackQueryHandler(telegram_bot.button_callback))
    tg_app.add_error_handler(telegram_bot.error_handler)

    await tg_app.initialize()
    await tg_app.start()

    async def notify_user(chat_id: int, message: str):
        # Check for image tags at the beginning of the message
        if message.startswith("[IMAGE:up]"):
            img = "up.jpg"
            # Remove the tag and the newline that follows
            text = message[len("[IMAGE:up]"):].lstrip("\n")
        elif message.startswith("[IMAGE:down]"):
            img = "down.jpg"
            text = message[len("[IMAGE:down]"):].lstrip("\n")
        elif message.startswith("[IMAGE:win]"):
            img = "win.jpg"
            text = message[len("[IMAGE:win]"):].lstrip("\n")
        else:
            # Plain text message (errors, status, etc.)
            await tg_app.bot.send_message(chat_id=chat_id, text=message)
            return

        path = Path(img)
        if path.exists():
            try:
                with open(path, "rb") as f:
                    await tg_app.bot.send_photo(
                        chat_id=chat_id,
                        photo=InputFile(f, filename=img),
                        caption=text,
                        parse_mode="HTML"
                    )
            except Exception as e:
                print(f"Image send error: {e}")
                await tg_app.bot.send_message(chat_id=chat_id, text=text)
        else:
            # Image missing, fallback to plain text
            await tg_app.bot.send_message(chat_id=chat_id, text=text)

    session_manager.set_notifier(notify_user)
    await tg_app.updater.start_polling()
    await session_manager.restore_auto_sessions()

    try:
        await asyncio.Event().wait()
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass