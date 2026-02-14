import logging
import os
import random
import sqlite3
import math
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.error import NetworkError, Conflict

# Load environment variables
load_dotenv()

# Define conversation states
ASK_NAME = 1

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Silence httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle specific exceptions."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(context.error, NetworkError):
        logger.warning("Network error encountered. Check your internet connection.")
    elif isinstance(context.error, Conflict):
        logger.error("Conflict Error: Another instance of this bot is already running!")
        logger.error("Please stop the other instance before running this one.")

# Token from .env
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

# Database column mapping
LEVEL_COLUMNS = {
    "school": "school_points",
    "uni": "uni_points",
}

# Database setup
def init_db():
    with sqlite3.connect("math_game.db") as conn:
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
        # Check if columns exist (for migration)
        cursor.execute("PRAGMA table_info(students)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'school_points' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN school_points INTEGER DEFAULT 0")
        if 'uni_points' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN uni_points INTEGER DEFAULT 0")
        conn.commit()

def update_high_score(user_id, score, level):
    column = LEVEL_COLUMNS[level]
    with sqlite3.connect("math_game.db") as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {column} FROM students WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        current_high = result[0] if result else 0

        if score > current_high:
            cursor.execute(
                f"UPDATE students SET {column} = ? WHERE user_id = ?", (score, user_id)
            )
            conn.commit()

def get_points(user_id, level):
    column = LEVEL_COLUMNS[level]
    with sqlite3.connect("math_game.db") as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {column} FROM students WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

def is_registered(user_id):
    with sqlite3.connect("math_game.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

def register_user(user_id, username):
    with sqlite3.connect("math_game.db") as conn:
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
    column = LEVEL_COLUMNS[level]
    with sqlite3.connect("math_game.db") as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT username, {column} FROM students ORDER BY {column} DESC LIMIT 10")
        return cursor.fetchall()

# Game Logic
def generate_school_question():
    a = random.randint(1, 50)
    b = random.randint(1, 50)
    op = random.choice(['+', '-', '*', '/'])

    if op == '+':
        answer = a + b
        question_text = f"{a} + {b} = ?"
    elif op == '-':
        answer = a - b
        question_text = f"{a} - {b} = ?"
    elif op == '*':
        a = random.randint(1, 12)
        b = random.randint(1, 12)
        answer = a * b
        question_text = f"{a} * {b} = ?"
    else:  # Division
        b = random.randint(2, 10)
        answer = random.randint(1, 20)
        a = b * answer
        question_text = f"{a} / {b} = ?"

    return question_text, answer

def generate_university_question():
    topic = random.choice(['calc1', 'calc2', 'calc3', 'linalg', 'discrete'])

    if topic == 'calc1':
        a = random.randint(1, 5)
        n = random.randint(2, 3)
        x0 = random.randint(1, 3)
        answer = a * n * (x0 ** (n - 1))
        question_text = f"Calculus I: Calculate f'({x0}) for f(x) = {a}x^{n}"

    elif topic == 'calc2':
        n = random.randint(1, 3)
        divisor = n + 1
        factor = random.randint(1, 5)
        a = factor * divisor
        answer = int(a / (n + 1))
        question_text = f"Calculus II: Evaluate ∫(0 to 1) {a}x^{n} dx"

    elif topic == 'calc3':
        a = random.randint(1, 5)
        b = random.randint(1, 5)
        x0 = random.randint(1, 5)
        y0 = random.randint(1, 5)
        answer = 2 * a * x0
        question_text = f"Calculus III: For f(x,y) = {a}x^2 + {b}y^2, find ∂f/∂x at ({x0}, {y0})"

    elif topic == 'linalg':
        a = random.randint(-5, 5)
        b = random.randint(-5, 5)
        c = random.randint(-5, 5)
        d = random.randint(-5, 5)
        answer = a*d - b*c
        question_text = f"Linear Algebra: Find determinant | {a} {b} |\n                                | {c} {d} |"

    else:  # discrete
        n = random.randint(4, 8)
        k = random.randint(2, n-1)
        answer = math.comb(n, k)
        question_text = f"Discrete Math: Calculate C({n}, {k}) (Combinations)"

    return question_text, answer

def generate_options(answer, level):
    """Generate 4 unique answer options including the correct one."""
    options = {answer}

    if level == "uni":
        # University: wider range proportional to answer magnitude
        spread = max(20, abs(answer) // 2)
    else:
        spread = 10

    attempts = 0
    while len(options) < 4 and attempts < 100:
        offset = random.randint(-spread, spread)
        if offset != 0:
            options.add(answer + offset)
        attempts += 1

    # Fallback if not enough unique options generated
    fallback = 1
    while len(options) < 4:
        options.add(answer + spread + fallback)
        fallback += 1

    options_list = list(options)
    random.shuffle(options_list)
    return options_list

def generate_question(level):
    if level == "school":
        q_text, answer = generate_school_question()
    else:
        q_text, answer = generate_university_question()

    full_text = f"[{level.capitalize()}] {q_text}"
    options_list = generate_options(answer, level)

    return full_text, answer, options_list

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
        "You have 15-20 seconds ⏳ to answer each question.\n"
        "Type /play to start! 🚀\n"
        "Type /rating to see the leaderboard. 🏆"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Registration cancelled. Type /start to try again.")
    return ConversationHandler.END

async def show_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("School Rating", callback_data="rating_school")],
        [InlineKeyboardButton("University Rating", callback_data="rating_uni")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a leaderboard:", reply_markup=reply_markup)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_registered(user.id):
        await update.message.reply_text(
            "You are not registered yet! Type /start to register first. 📝"
        )
        return

    keyboard = [
        [InlineKeyboardButton("School Level", callback_data="start_school")],
        [InlineKeyboardButton("University Level", callback_data="start_uni")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select difficulty level:", reply_markup=reply_markup)

async def timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job queue callback for question timeout."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    user_id = job_data['user_id']
    q_num = job_data['q_num']
    user_data = job_data['user_data']

    if not user_data.get('game_active'):
        return
    if user_data.get('question_count') != q_num:
        return

    user_data['game_active'] = False
    final_score = user_data.get('score', 0)
    level = user_data.get('level', 'school')
    high_score = get_points(user_id, level)

    await context.bot.send_message(
        chat_id,
        text=f"⏰ Time's up! Game Over [{level.capitalize()} Mode].\nScore: {final_score}\nHigh Score: {high_score} 🏆\nType /play to try again. 🔄"
    )

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q_num = context.user_data.get('question_count', 1)
    level = context.user_data.get('level', 'school')

    q_text, answer, options = generate_question(level)

    context.user_data['current_answer'] = answer

    keyboard = [
        [InlineKeyboardButton(str(opt), callback_data=str(opt)) for opt in options[:2]],
        [InlineKeyboardButton(str(opt), callback_data=str(opt)) for opt in options[2:]]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"Question {q_num}: {q_text}"

    if update.callback_query:
        try:
            message = await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            message = await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        message = await update.message.reply_text(text, reply_markup=reply_markup)

    # Cancel any existing timer job for this user
    timeout_duration = 20 if level == 'uni' else 15
    job_name = f"timeout_{update.effective_user.id}"

    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    # Schedule new timeout via job_queue
    context.job_queue.run_once(
        timeout_callback,
        when=timeout_duration,
        name=job_name,
        data={
            'chat_id': message.chat_id,
            'user_id': update.effective_user.id,
            'q_num': q_num,
            'user_data': context.user_data,
        }
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    # Handle Rating Selection
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
        return

    # Handle Game Start Selection
    if data.startswith("start_"):
        level = "school" if data == "start_school" else "uni"
        context.user_data['level'] = level
        context.user_data['score'] = 0
        context.user_data['question_count'] = 1
        context.user_data['game_active'] = True
        await send_question(update, context)
        return

    if not context.user_data.get('game_active'):
        return

    # Cancel the timer
    job_name = f"timeout_{update.effective_user.id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    try:
        selected_answer = int(query.data)
    except ValueError:
        return

    correct_answer = context.user_data.get('current_answer')
    level = context.user_data.get('level', 'school')

    if selected_answer == correct_answer:
        context.user_data['score'] += 1
        context.user_data['question_count'] += 1

        update_high_score(update.effective_user.id, context.user_data['score'], level)
        await send_question(update, context)
    else:
        context.user_data['game_active'] = False
        final_score = context.user_data['score']
        high_score = get_points(update.effective_user.id, level)

        await query.message.edit_text(
            f"❌ Wrong! The answer was {correct_answer}.\n"
            f"Game Over [{level.capitalize()} Mode] 💀.\n"
            f"Score: {final_score} 📉\n"
            f"High Score: {high_score} 🏆\n"
            "Type /play to try again. 🔄"
        )

def main() -> None:
    """Run the bot."""
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
