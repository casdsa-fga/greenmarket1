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
WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://casdsa-fga.github.io/greenmarket1/"
)

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


# ================= DEBUG =================
def debug(msg):
    print(f"[DEBUG] {msg}", flush=True)


# ================= SEND MESSAGE =================
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
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

    debug(f"RAW: {data}")

    if not data or "message" not in data:
        return jsonify({"ok": True})

    message = data["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")

    debug(f"CHAT={chat_id} TEXT={text}")

    referrer_id = None

    # ===== /start =====
    if text.startswith("/start"):
        parts = text.split(" ", 1)

        if len(parts) == 2:
            referrer_id = parts[1].strip()

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
        existing = c.fetchone()

        if not existing:

            if referrer_id == chat_id:
                referrer_id = None

            debug(f"INSERT USER {chat_id} REF {referrer_id}")

            c.execute(
                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                (chat_id, referrer_id),
            )

            # ===== REF BONUS =====
            if referrer_id:
                c.execute(
                    "SELECT user_id FROM users WHERE user_id=?",
                    (referrer_id,)
                )
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

                        # уведомление рефереру
                        send_message(
                            referrer_id,
                            "🎉 Новый реферал!\n💰 +300 ₽\n🎯 +50 тикетов"
                        )

        conn.commit()
        conn.close()

        webapp_ref = referrer_id if referrer_id else chat_id

        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 Открыть GREEN MARKET",
                "web_app": {"url": f"{WEBAPP_URL}?ref={webapp_ref}"}
            }]]
        }

        # ===== ВАЖНЫЙ WELCOME ТЕКСТ =====
        welcome_text = (
            "🌿 Добро пожаловать в GREEN MARKET!\n\n"
            "💰 Зарабатывай на приглашениях\n"
            "👥 +300 ₽ за друга\n"
            "🎯 +50 тикетов в рейтинг\n"
            "⚡ Начни прямо сейчас!\n\n"
            "👇 Открой приложение ниже"
        )

        send_message(chat_id, welcome_text, keyboard)

    return jsonify({"ok": True})


# ================= HOME =================
@app.route("/")
def home():
    return "OK"


# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
