import hashlib
import hmac
import json
import os
import random
import sqlite3
import time
from urllib.parse import parse_qs

from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request

load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

DB_FILE = os.getenv("DB_FILE", "math_game.db")

# Level -> DB column mapping
LEVEL_COLUMNS = {
    "school_easy": "school_points",
    "school_medium": "school_points",
    "uni_calculus": "uni_points",
    "uni_linalg": "uni_points",
    "uni_discrete": "uni_points",
    "mixed": "school_points",
}


# ── Telegram WebApp initData validation ──────────────────────────────────────

def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData using HMAC-SHA256.

    Returns parsed user dict on success, None on failure.
    """
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Build data-check-string: sorted key=value pairs excluding 'hash'
        data_pairs = []
        for key, values in parsed.items():
            if key == "hash":
                continue
            data_pairs.append(f"{key}={values[0]}")
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)

        # HMAC-SHA256: secret_key = HMAC_SHA256("WebAppData", BOT_TOKEN)
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            return None

        # Parse user JSON
        user_json = parsed.get("user", [None])[0]
        if not user_json:
            return None

        return json.loads(user_json)
    except Exception:
        return None


def get_telegram_user() -> dict | None:
    """Extract and validate Telegram user from request header or body."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        data = request.get_json(silent=True)
        if data:
            init_data = data.get("initData", "")
    if not init_data:
        init_data = request.args.get("initData", "")

    if not init_data:
        return None
    return validate_init_data(init_data)


# ── Database ────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS students (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            school_points INTEGER DEFAULT 0,
            uni_points INTEGER DEFAULT 0
        )"""
    )
    c.execute("PRAGMA table_info(students)")
    columns = [info[1] for info in c.fetchall()]
    if "school_points" not in columns:
        c.execute("ALTER TABLE students ADD COLUMN school_points INTEGER DEFAULT 0")
    if "uni_points" not in columns:
        c.execute("ALTER TABLE students ADD COLUMN uni_points INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def ensure_user(user_id: int, username: str):
    """Register user if not exists, update username if changed."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute("UPDATE students SET username = ? WHERE user_id = ?", (username, user_id))
    else:
        c.execute(
            "INSERT INTO students (user_id, username) VALUES (?, ?)", (user_id, username)
        )
    conn.commit()
    conn.close()


def get_score(user_id: int, level_key: str) -> int:
    column = LEVEL_COLUMNS.get(level_key, "school_points")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"SELECT {column} FROM students WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def save_score(user_id: int, username: str, score: int, level_key: str):
    column = LEVEL_COLUMNS.get(level_key, "school_points")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute(
            f"UPDATE students SET {column} = CASE WHEN ? > {column} THEN ? ELSE {column} END WHERE user_id = ?",
            (score, score, user_id),
        )
    else:
        c.execute(
            f"INSERT INTO students (user_id, username, {column}) VALUES (?, ?, ?)",
            (user_id, username, score),
        )
    conn.commit()
    conn.close()


def get_leaderboard(level_key: str = "school", limit: int = 10) -> list:
    if level_key in ("school", "school_easy", "school_medium"):
        column = "school_points"
    else:
        column = "uni_points"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        f"SELECT username, {column} FROM students ORDER BY {column} DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "score": r[1]} for r in rows]


# ── Question generators ─────────────────────────────────────────────────────

def _school_easy() -> tuple:
    a, b = random.randint(1, 50), random.randint(1, 50)
    op = random.choice(["+", "-", "*"])
    answer = eval(f"{a}{op}{b}")
    return f"{a} {op} {b} = ?", int(answer)


def _school_medium() -> tuple:
    kind = random.choice(["div", "pow", "mixed"])
    if kind == "div":
        b = random.randint(2, 12)
        answer = random.randint(1, 20)
        a = b * answer
        return f"{a} \u00f7 {b} = ?", answer
    elif kind == "pow":
        base = random.randint(2, 9)
        exp = random.randint(2, 3)
        answer = base ** exp
        return f"{base}^{exp} = ?", answer
    else:
        a, b, c = random.randint(1, 20), random.randint(1, 10), random.randint(1, 10)
        answer = a + b * c
        return f"{a} + {b} \u00d7 {c} = ?", answer


def _university_calculus() -> tuple:
    problems = [
        ("d/dx (x\u00b2) at x=3 = ?", 6),
        ("d/dx (x\u00b3) at x=2 = ?", 12),
        ("d/dx (5x\u00b2) at x=1 = ?", 10),
        ("d/dx (x\u2074) at x=1 = ?", 4),
        ("d/dx (3x\u00b2 + 2x) at x=2 = ?", 14),
        ("d/dx (x\u00b3 \u2212 x) at x=1 = ?", 2),
        ("\u222b 2x dx from 0 to 3 = ?", 9),
        ("\u222b 1 dx from 0 to 5 = ?", 5),
        ("\u222b 3x\u00b2 dx from 0 to 2 = ?", 8),
        ("d/dx (4x\u00b3) at x=1 = ?", 12),
    ]
    return random.choice(problems)


def _university_linalg() -> tuple:
    problems = [
        ("det [[2,3],[1,4]] = ?", 5),
        ("det [[1,0],[0,1]] = ?", 1),
        ("det [[3,8],[4,6]] = ?", -14),
        ("det [[5,1],[3,2]] = ?", 7),
        ("det [[2,0],[0,3]] = ?", 6),
        ("Trace of [[1,2],[3,4]] = ?", 5),
        ("Trace of [[5,0],[0,7]] = ?", 12),
        ("det [[1,2,0],[0,1,0],[0,0,3]] = ?", 3),
        ("det [[2,1],[1,2]] = ?", 3),
        ("Rank of [[1,0],[0,0]] = ?", 1),
    ]
    return random.choice(problems)


def _university_discrete() -> tuple:
    problems = [
        ("5! = ?", 120),
        ("C(6,2) = ?", 15),
        ("C(5,3) = ?", 10),
        ("P(4,2) = ?", 12),
        ("4! = ?", 24),
        ("C(7,3) = ?", 35),
        ("C(8,2) = ?", 28),
        ("6! / 4! = ?", 30),
        ("C(10,1) = ?", 10),
        ("P(5,3) = ?", 60),
    ]
    return random.choice(problems)


def _mixed() -> tuple:
    gen = random.choice([
        _school_easy, _school_medium,
        _university_calculus, _university_linalg, _university_discrete,
    ])
    return gen()


LEVELS = {
    "school_easy":   {"label": "School \u2013 Easy",          "gen": _school_easy,          "timer": 15, "points": 1},
    "school_medium": {"label": "School \u2013 Medium",        "gen": _school_medium,        "timer": 15, "points": 2},
    "uni_calculus":  {"label": "University \u2013 Calculus",   "gen": _university_calculus,  "timer": 20, "points": 3},
    "uni_linalg":    {"label": "University \u2013 Linear Alg", "gen": _university_linalg,   "timer": 20, "points": 3},
    "uni_discrete":  {"label": "University \u2013 Discrete",   "gen": _university_discrete, "timer": 20, "points": 3},
    "mixed":         {"label": "Mixed \u2013 All Levels",      "gen": _mixed,                "timer": 20, "points": 2},
}


def _build_choices(correct: int, count: int = 4) -> list:
    choices = {correct}
    while len(choices) < count:
        offset = random.randint(1, max(10, abs(correct)))
        choices.add(correct + random.choice([-1, 1]) * offset)
    result = list(choices)
    random.shuffle(result)
    return result


# ── In-memory game state (keyed by user_id) ─────────────────────────────────
# Replaces Flask session — needed because Telegram WebApp doesn't share cookies
game_state: dict[int, dict] = {}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/question", methods=["POST"])
def get_question():
    user = get_telegram_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = user["id"]
    username = user.get("first_name", user.get("username", "Player"))
    ensure_user(user_id, username)

    data = request.json
    level_key = data.get("level", "school_easy")
    if level_key not in LEVELS:
        return jsonify({"error": "Invalid level"}), 400

    level = LEVELS[level_key]
    question, answer = level["gen"]()
    choices = _build_choices(answer)

    game_state[user_id] = {
        "answer": answer,
        "level": level_key,
        "time_start": time.time(),
    }

    return jsonify({
        "question": question,
        "choices": choices,
        "timer": level["timer"],
        "label": level["label"],
        "points": level["points"],
    })


@app.route("/api/answer", methods=["POST"])
def check_answer():
    user = get_telegram_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = user["id"]
    username = user.get("first_name", user.get("username", "Player"))

    data = request.json
    chosen = data.get("answer")

    state = game_state.pop(user_id, None)
    if not state:
        return jsonify({"error": "No active question"}), 400

    correct = state["answer"]
    level_key = state["level"]
    time_start = state["time_start"]

    timer = LEVELS[level_key]["timer"]
    elapsed = time.time() - time_start

    if elapsed > timer + 1:
        return jsonify({
            "correct": False,
            "timeout": True,
            "answer": correct,
            "score": get_score(user_id, level_key),
        })

    if chosen == correct:
        pts = LEVELS[level_key]["points"]
        new_score = get_score(user_id, level_key) + pts
        save_score(user_id, username, new_score, level_key)
        return jsonify({
            "correct": True,
            "timeout": False,
            "points": pts,
            "score": new_score,
        })
    else:
        return jsonify({
            "correct": False,
            "timeout": False,
            "answer": correct,
            "score": get_score(user_id, level_key),
        })


@app.route("/api/leaderboard")
def leaderboard():
    level = request.args.get("level", "school")
    return jsonify(get_leaderboard(level))


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
