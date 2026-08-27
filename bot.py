import os
import re
import sqlite3
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================

TOKEN = os.environ["BOT_TOKEN"]

DB = "links.db"

BD_TZ = ZoneInfo("Asia/Dhaka")

PORT = int(os.environ.get("PORT", 10000))

# Render automatically provides this
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not RENDER_URL:
    raise RuntimeError(
        "RENDER_EXTERNAL_URL environment variable not found."
    )

WEBHOOK_URL = f"{RENDER_URL}/telegram"


# =========================
# DATABASE
# =========================

conn = sqlite3.connect(
    DB,
    check_same_thread=False
)

conn.execute("""
CREATE TABLE IF NOT EXISTS links (
    url TEXT PRIMARY KEY,
    first_date TEXT NOT NULL,
    first_user TEXT NOT NULL
)
""")

conn.commit()


# =========================
# URL NORMALIZER
# =========================

def normalize_url(url):
    url = url.strip().rstrip(".,!?;:)")
    return url.lower()


# =========================
# TELEGRAM LINK CHECKER
# =========================

async def check_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    text = update.message.text

    # Find URLs
    urls = re.findall(
        r'https?://[^\s<>"\']+',
        text
    )

    # একই মেসেজে একই লিংক একাধিকবার থাকলে একবারই পরীক্ষা
    urls = list(dict.fromkeys(
        normalize_url(url)
        for url in urls
    ))

    for url in urls:

        # শুধু Facebook / fb.watch
        if (
            "facebook.com" not in url
            and "fb.watch" not in url
        ):
            continue

        user = update.effective_user

        username = (
            f"@{user.username}"
            if user and user.username
            else (
                user.full_name
                if user
                else "Unknown"
            )
        )

        # =========================
        # CHECK DATABASE
        # =========================

        row = conn.execute(
            """
            SELECT first_date, first_user
            FROM links
            WHERE url = ?
            """,
            (url,)
        ).fetchone()

        # =========================
        # DUPLICATE LINK
        # =========================

        if row:

            first_date, first_user = row

            await update.message.reply_text(
                "⚠️ এই লিংকটি আগে ব্যবহার করা হয়েছে।\n\n"
                "🚫 একই লিংক দ্বিতীয়বার ব্যবহার করবেন না।\n"
                "🔗 অনুগ্রহ করে নতুন লিংক ব্যবহার করুন।\n\n"
                f"📅 প্রথম পাঠানো: {first_date}\n"
                f"👤 প্রথম পাঠিয়েছেন: {first_user}"
            )

        # =========================
        # NEW LINK
        # =========================

        else:

            now = datetime.now(BD_TZ)

            first_date = now.strftime(
                "%d-%m-%Y %I:%M %p"
            )

            conn.execute(
                """
                INSERT INTO links
                (url, first_date, first_user)
                VALUES (?, ?, ?)
                """,
                (
                    url,
                    first_date,
                    username
                )
            )

            conn.commit()

            # নতুন লিংকে কোনো reply নেই


# =========================
# FLASK
# =========================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Facebook Link Checker Bot is running!"


@web_app.route("/health")
def health():
    return "OK"


# =========================
# TELEGRAM APPLICATION
# =========================

telegram_app = (
    Application.builder()
    .token(TOKEN)
    .build()
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        check_link
    )
)


# =========================
# ASYNCIO LOOP
# =========================

loop = asyncio.new_event_loop()


async def telegram_runner():

    await telegram_app.initialize()

    await telegram_app.start()

    # Remove old webhook first
    await telegram_app.bot.delete_webhook()

    # Set new webhook
    await telegram_app.bot.set_webhook(
        url=WEBHOOK_URL
    )

    print(
        f"Telegram webhook set to: {WEBHOOK_URL}"
    )

    # Keep Telegram application running
    await asyncio.Event().wait()


def start_telegram():

    asyncio.set_event_loop(loop)

    loop.run_until_complete(
        telegram_runner()
    )


# =========================
# WEBHOOK ENDPOINT
# =========================

@web_app.route(
    "/telegram",
    methods=["POST"]
)
def telegram_webhook():

    try:

        data = request.get_json(
            force=True
        )

        update = Update.de_json(
            data,
            telegram_app.bot
        )

        future = asyncio.run_coroutine_threadsafe(
            telegram_app.process_update(update),
            loop
        )

        future.result(
            timeout=30
        )

        return "OK", 200

    except Exception as e:

        print(
            f"Webhook error: {e}"
        )

        return "ERROR", 500


# =========================
# MAIN
# =========================

def main():

    # Start Telegram in background thread
    telegram_thread = threading.Thread(
        target=start_telegram,
        daemon=True
    )

    telegram_thread.start()

    print(
        f"Starting web server on port {PORT}"
    )

    # Start Render web server
    web_app.run(
        host="0.0.0.0",
        port=PORT
    )


# =========================
# START
# =========================

if __name__ == "__main__":
    main()
