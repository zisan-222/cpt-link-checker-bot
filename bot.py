import os
import re
import sqlite3
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters


TOKEN = os.environ["BOT_TOKEN"]

DB = "links.db"

conn = sqlite3.connect(DB, check_same_thread=False)

conn.execute("""
CREATE TABLE IF NOT EXISTS links (
    url TEXT PRIMARY KEY,
    first_date TEXT NOT NULL,
    first_user TEXT NOT NULL
)
""")

conn.commit()


def normalize_url(url):
    url = url.strip().rstrip(".,!?;:)")
    return url.lower()


async def check_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text

    urls = re.findall(r'https?://[^\s<>"\']+', text)

    for url in urls:

        url = normalize_url(url)

        # শুধু Facebook URL পরীক্ষা করবে
        if "facebook.com" not in url and "fb.watch" not in url:
            continue

        user = update.effective_user

        username = (
            f"@{user.username}"
            if user and user.username
            else (user.full_name if user else "Unknown")
        )

        row = conn.execute(
            "SELECT first_date, first_user FROM links WHERE url = ?",
            (url,)
        ).fetchone()

        # একই লিংক আগে থাকলে শুধু তখন রিপ্লাই করবে
        if row:

            first_date, first_user = row

            await update.message.reply_text(
                "⚠️ এই লিংকটি আগে ব্যবহার করা হয়েছে।\n\n"
                "🚫 একই লিংক দ্বিতীয়বার ব্যবহার করবেন না।\n"
                "🔗 অনুগ্রহ করে নতুন লিংক ব্যবহার করুন।\n\n"
                f"📅 প্রথম পাঠানো: {first_date}\n"
                f"👤 প্রথম পাঠিয়েছেন: {first_user}"
            )

        else:

            # নতুন লিংক হলে ডাটাবেজে সংরক্ষণ করবে
            # কিন্তু কোনো রিপ্লাই দেবে না
            now = datetime.now(timezone.utc).strftime(
                "%d-%m-%Y %H:%M UTC"
            )

            conn.execute(
                """
                INSERT INTO links (url, first_date, first_user)
                VALUES (?, ?, ?)
                """,
                (url, now, username)
            )

            conn.commit()


def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            check_link
        )
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
