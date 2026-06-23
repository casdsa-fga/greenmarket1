import os
import hashlib
import hmac
import json
import time
import urllib.parse
import sqlite3

from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get(
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

# ================= TELEGRAM SEND =================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=5
    )

# ================= /START + REF SYSTEM =================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    debug(f"RAW: {data}")

    if not data or "message" not in data:
        return jsonify({"ok": True})

    chat_id = str(data["message"]["chat"]["id"])
    text = data["message"].get("text", "")

    debug(f"CHAT={chat_id} TEXT={text}")

    referrer_id = None

    # -------- START --------
    if text.startswith("/start"):
        parts = text.split(" ", 1)

        if len(parts) == 2:
            referrer_id = str(parts[1].strip())

        debug(f"REF RAW={referrer_id}")

        conn = get_db()
        c = conn.cursor()

        # проверка пользователя
        c.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
        existing = c.fetchone()

        if not existing:

            # защита от саморефа
            if referrer_id == chat_id:
                referrer_id = None

            debug(f"INSERT USER {chat_id} REF {referrer_id}")

            c.execute(
                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                (chat_id, referrer_id),
            )

            # -------- REF BONUS --------
            if referrer_id:

                # проверяем что реферер существует
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

                    debug(f"ALREADY={already}")

                    if not already:
                        debug("ADDING BONUS")

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

                else:
                    debug("REFERRER NOT FOUND IN DB")

        conn.commit()
        conn.close()

    webapp_ref = referrer_id if referrer_id else chat_id

    keyboard = {
        "inline_keyboard": [[{
            "text": "🚀 Open App",
            "web_app": {
                "url": f"{WEBAPP_URL}?ref={webapp_ref}"
            }
        }]]
    }

    send_message(
        chat_id,
        "🌿 Welcome!",
        reply_markup=keyboard
    )

    return jsonify({"ok": True})


# ================= HOME =================

@app.route("/")
def home():
    return "Bot is running ✅"


# ================= RUN =================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
