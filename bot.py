import os
import hashlib
import hmac
import json
import urllib.parse
import sqlite3
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://casdsa-fga.github.io/greenmarket1/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

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
        referrer_id TEXT,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invited INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS referral_earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id TEXT,
        referred_user_id TEXT,
        UNIQUE(referrer_id, referred_user_id)
    )
    """)

    conn.commit()
    conn.close()


init_db()

# ================= TELEGRAM =================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=5
    )

# ================= WEBHOOK =================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    if not data or "message" not in data:
        return jsonify({"ok": True})

    chat_id = str(data["message"]["chat"]["id"])
    text = data["message"].get("text", "")

    conn = get_db()
    c = conn.cursor()

    # ================= START =================
    if text.startswith("/start"):
        parts = text.split(" ", 1)
        referrer_id = parts[1].strip() if len(parts) == 2 else None

        if referrer_id == chat_id:
            referrer_id = None

        c.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
        exists = c.fetchone()

        if not exists:
            c.execute(
                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                (chat_id, referrer_id)
            )

            if referrer_id:
                c.execute("SELECT user_id FROM users WHERE user_id=?", (referrer_id,))
                ref_exists = c.fetchone()

                if ref_exists:
                    c.execute("""
                        SELECT 1 FROM referral_earnings
                        WHERE referrer_id=? AND referred_user_id=?
                    """, (referrer_id, chat_id))

                    already = c.fetchone()

                    if not already:
                        c.execute("""
                            UPDATE users
                            SET balance = balance + 300,
                                tickets = tickets + 50,
                                invited = invited + 1
                            WHERE user_id=?
                        """, (referrer_id,))

                        c.execute("""
                            INSERT INTO referral_earnings (referrer_id, referred_user_id)
                            VALUES (?, ?)
                        """, (referrer_id, chat_id))

        conn.commit()
        conn.close()

        webapp_ref = referrer_id if referrer_id else chat_id

        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 Открыть GREEN MARKET",
                "web_app": {"url": f"{WEBAPP_URL}?ref={webapp_ref}"}
            }]]
        }

        send_message(
            chat_id,
            "🌿 <b>Добро пожаловать в GREEN MARKET!</b>\n\n💰 Начни зарабатывать уже сейчас.",
            keyboard
        )

    return jsonify({"ok": True})


# ================= USER API (ВАЖНО ДЛЯ JS) =================

@app.route("/user/<user_id>")
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()

    if not user:
        return jsonify({
            "balance": 0,
            "tickets": 0,
            "invited": 0
        })

    return jsonify({
        "balance": user["balance"],
        "tickets": user["tickets"],
        "invited": user["invited"]
    })


# ================= HOME =================

@app.route("/")
def home():
    return "GREEN MARKET OK"


# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
