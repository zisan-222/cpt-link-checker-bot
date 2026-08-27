import os
import re
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask
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

# Bangladesh Time
BD_TZ = ZoneInfo("Asia/Dhaka")

# Render port
PORT = int(os.environ.get("PORT", 10000))


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

async def check_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text

    # Find URLs
    urls = re.findall(
        r'https?://[^\s<>"\']+',
        text
    )

    # একই মেসেজে একই লিংক একাধিকবার থাকলে একবারই পরীক্ষা করবে
    urls = list(dict.fromkeys(
        normalize_url(url)
        for url in urls
    ))

    for url in urls:

        # শুধু Facebook / fb.watch লিংক পরীক্ষা করবে
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

            # Bangladesh local time
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

            # নতুন লিংকের জন্য কোনো reply যাবে না
            # শুধু database-এ save হবে


# =========================
# FLASK WEB SERVER
# =========================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Facebook Link Checker Bot is running!"


@web_app.route("/health")
def health():
    return "OK"


def run_web_server():
    web_app.run(
        host="0.0.0.0",
        port=PORT
    )


# =========================
# MAIN
# =========================

def main():

    # Render Web Service-এর জন্য HTTP server
    server_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    server_thread.start()

    # Telegram bot
    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            check_link
        )
    )

    print("Bot is running...")

    app.run_polling()


# =========================
# START
# =========================

if __name__ == "__main__":
    main()
