import os
import hashlib
import hmac
import json
import time
import urllib.parse

from flask import Flask, request, jsonify
import requests
import sqlite3
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://casdsa-fga.github.io/greenmarket1/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment / .env")


# ===== DATABASE =====

def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id   TEXT PRIMARY KEY,
            referrer_id TEXT,
            balance   INTEGER DEFAULT 0,
            tickets   INTEGER DEFAULT 0,
            invited   INTEGER DEFAULT 0,
            registered INTEGER DEFAULT 1,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_earnings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id      TEXT NOT NULL,
            referred_user_id TEXT NOT NULL,
            amount           INTEGER DEFAULT 300,
            earned_at        INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(referrer_id, referred_user_id)
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ===== TELEGRAM initData VALIDATION =====

def validate_init_data(init_data_raw: str) -> dict | None:
    """
    Validate Telegram WebApp initData.
    Returns parsed user dict on success, None on failure.
    """
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        expected_hash = hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            return None

        # Optional: check auth_date freshness (5 min window)
        auth_date = int(parsed.get("auth_date", 0))
        if time.time() - auth_date > 300:
            return None

        user_data = json.loads(parsed.get("user", "{}"))
        return user_data
    except Exception:
        return None


# ===== TELEGRAM HELPER =====

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=5,
    )


# ===== WEBHOOK =====

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"status": "ok"})

    chat_id = str(data["message"]["chat"]["id"])
    text = data["message"].get("text", "")

    referrer_id = None
    if text.startswith("/start"):
        parts = text.split(" ", 1)
        if len(parts) > 1:
            referrer_id = parts[1].strip()

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT user_id FROM users WHERE user_id = ?", (chat_id,))
        existing = c.fetchone()

        if not existing:
            # Prevent self-referral
            if referrer_id == chat_id:
                referrer_id = None

            c.execute(
                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                (chat_id, referrer_id),
            )

            if referrer_id:
                c.execute(
                    "SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?",
                    (referrer_id, chat_id),
                )
                if not c.fetchone():
                    c.execute(
                        "UPDATE users SET balance = balance + 300, tickets = tickets + 50, invited = invited + 1 WHERE user_id = ?",
                        (referrer_id,),
                    )
                    c.execute(
                        "INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)",
                        (referrer_id, chat_id),
                    )
                    app.logger.info("Bonus awarded: %s invited %s", referrer_id, chat_id)

        conn.commit()
        conn.close()

    keyboard = {
        "inline_keyboard": [[{
            "text": "🚀 Открыть приложение",
            "web_app": {"url": f"{WEBAPP_URL}?ref={chat_id}"},
        }]]
    }

    send_message(
        chat_id,
        "🌿 Добро пожаловать в Green Market!\n💰 Зарабатывай с друзьями!",
        reply_markup=keyboard,
    )
    return jsonify({"status": "ok"})


# ===== REGISTRATION ENDPOINT (called from Mini App) =====

@app.route("/api/register", methods=["POST"])
def register():
    """
    Register a user via the Mini App.
    Expects JSON:
      {
        "init_data": "<raw Telegram WebApp initData string>",
        "referrer_id": "<optional referrer user_id>"
      }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    init_data_raw = body.get("init_data", "")
    referrer_id = str(body.get("referrer_id", "")).strip() or None

    # --- Validate initData ---
    user_data = validate_init_data(init_data_raw)
    if not user_data:
        return jsonify({"status": "error", "message": "Invalid initData"}), 403

    user_id = str(user_data.get("id", ""))
    if not user_id:
        return jsonify({"status": "error", "message": "No user_id in initData"}), 400

    # Prevent self-referral
    if referrer_id == user_id:
        referrer_id = None

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing = c.fetchone()

    if existing:
        conn.close()
        return jsonify({"status": "already_registered"}), 200

    c.execute(
        "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
        (user_id, referrer_id),
    )

    bonus_awarded = False
    if referrer_id:
        # Make sure referrer exists
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        referrer_exists = c.fetchone()

        if referrer_exists:
            c.execute(
                "SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?",
                (referrer_id, user_id),
            )
            if not c.fetchone():
                c.execute(
                    "UPDATE users SET balance = balance + 300, tickets = tickets + 50, invited = invited + 1 WHERE user_id = ?",
                    (referrer_id,),
                )
                c.execute(
                    "INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)",
                    (referrer_id, user_id),
                )
                bonus_awarded = True

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "bonus_awarded": bonus_awarded,
    })


# ===== USER STATS ENDPOINT (optional, for Mini App to display real data) =====

@app.route("/api/stats", methods=["POST"])
def stats():
    """
    Return balance/tickets/invites for a validated user.
    Expects JSON: { "init_data": "..." }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error"}), 400

    user_data = validate_init_data(body.get("init_data", ""))
    if not user_data:
        return jsonify({"status": "error", "message": "Invalid initData"}), 403

    user_id = str(user_data.get("id", ""))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance, tickets, invited FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "not_found"}), 404

    return jsonify({
        "status": "ok",
        "balance": row["balance"],
        "tickets": row["tickets"],
        "invited": row["invited"],
    })


@app.route("/")
def home():
    return "Бот работает! ✅"



import os

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(
            os.getenv(
                'PORT',
                8080
            )
        )
    )
