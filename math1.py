import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.error import NetworkError, Conflict

# Load environment variables
load_dotenv()

# Define conversation states
ASK_NAME = 1

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(context.error, NetworkError):
        logger.warning("Network error encountered. Check your internet connection.")
    elif isinstance(context.error, Conflict):
        logger.error("Conflict Error: Another instance of this bot is already running!")


# Token & WebApp URL from .env
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

WEBAPP_URL = os.getenv("WEBAPP_URL")
if not WEBAPP_URL:
    raise ValueError("WEBAPP_URL is not set in .env file")

DB_FILE = os.getenv("DB_FILE", "math_game.db")


# ── Database ─────────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                school_points INTEGER DEFAULT 0,
                uni_points INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute("PRAGMA table_info(students)")
        columns = [info[1] for info in cursor.fetchall()]
        if "school_points" not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN school_points INTEGER DEFAULT 0")
        if "uni_points" not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN uni_points INTEGER DEFAULT 0")
        conn.commit()


def is_registered(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


def register_user(user_id, username):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute("UPDATE students SET username = ? WHERE user_id = ?", (username, user_id))
        else:
            cursor.execute(
                "INSERT INTO students (user_id, username) VALUES (?, ?)", (user_id, username)
            )
        conn.commit()


def get_leaderboard(level):
    column = "school_points" if level == "school" else "uni_points"
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT username, {column} FROM students ORDER BY {column} DESC LIMIT 10"
        )
        return cursor.fetchall()


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! 👋\nWelcome to the Math Game! 🎮\n"
        "Please enter your name for the leaderboard: 📝"
    )
    return ASK_NAME


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    name = update.message.text

    register_user(user.id, name)

    await update.message.reply_text(
        f"Thanks {name}! You are registered. ✅\n"
        "Type /play to start the game! 🚀\n"
        "Type /rating to see the leaderboard. 🏆"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Registration cancelled. Type /start to try again.")
    return ConversationHandler.END


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_registered(user.id):
        await update.message.reply_text(
            "You are not registered yet! Type /start to register first. 📝"
        )
        return

    keyboard = [
        [InlineKeyboardButton("🎮 Play Math Game", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Click the button below to open the game! 🚀",
        reply_markup=reply_markup,
    )


async def show_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("School Rating", callback_data="rating_school")],
        [InlineKeyboardButton("University Rating", callback_data="rating_uni")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a leaderboard:", reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("rating_"):
        level = "school" if data == "rating_school" else "uni"
        top_players = get_leaderboard(level)
        title = "School Leaderboard 🎓" if level == "school" else "University Leaderboard 🏛️"

        if not top_players:
            text = f"🏆 *{title}* 🏆\nNo players yet!"
        else:
            text = f"🏆 *{title}* 🏆\n\n"
            for i, (name, points) in enumerate(top_players, 1):
                safe_name = name.replace("*", "").replace("_", "")
                text += f"{i}. {safe_name}: {points} points\n"

        await query.message.edit_text(text, parse_mode="Markdown")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    init_db()

    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("rating", show_rating))
    application.add_handler(CallbackQueryHandler(button))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
