import os
import sqlite3
import json
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

# ================= DB =================

def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invited INTEGER DEFAULT 0,
        referrer_id TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()

# ================= TELEGRAM =================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload
    )

# ================= WEBHOOK =================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"ok": True})

    msg = data["message"]
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "")

    conn = get_db()
    c = conn.cursor()

    # ================= /start =================
    if text.startswith("/start"):

        parts = text.split(" ")
        ref = parts[1] if len(parts) > 1 else None

        c.execute("SELECT * FROM users WHERE user_id=?", (chat_id,))
        user = c.fetchone()

        if not user:
            c.execute(
                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                (chat_id, ref)
            )

        conn.commit()

        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "🚀 Открыть маркет",
                    "web_app": {"url": WEBAPP_URL}
                }
            ]]
        }

        send_message(
            chat_id,
            "🌿 Добро пожаловать в GREEN MARKET!\n\nЗарабатывай на приглашениях 👥",
            keyboard
        )

    conn.close()
    return jsonify({"ok": True})


# ================= USER API (ВАЖНО ДЛЯ JS) =================

@app.route("/user/<user_id>")
def user(user_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()

    if not row:
        return jsonify({"balance": 0, "tickets": 0, "invited": 0})

    return jsonify({
        "balance": row["balance"],
        "tickets": row["tickets"],
        "invited": row["invited"]
    })


# ================= HOME =================

@app.route("/")
def home():
    return "OK"


# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
