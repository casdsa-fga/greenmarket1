bash

cat > /mnt/user-data/outputs/bot.py << 'ENDOFFILE'
import os
import hashlib
import hmac
import json
import time
import urllib.parse
import logging

from flask import Flask, request, jsonify
import requests
import sqlite3
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://casdsa-fga.github.io/greenmarket1/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Create a .env file with BOT_TOKEN=...")


# ──────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect("users.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     TEXT PRIMARY KEY,
            referrer_id TEXT,
            balance     INTEGER DEFAULT 0,
            tickets     INTEGER DEFAULT 0,
            invited     INTEGER DEFAULT 0,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_earnings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id      TEXT NOT NULL,
            referred_user_id TEXT NOT NULL,
            earned_at        INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(referrer_id, referred_user_id)
        )
    """)
    conn.commit()
    conn.close()
    log.info("DB ready")


init_db()


# ──────────────────────────────────────────────────────────────────
# initData VALIDATION
# ──────────────────────────────────────────────────────────────────

def validate_init_data(raw: str) -> dict | None:
    """Validate Telegram WebApp initData. Returns user dict or None."""
    try:
        parsed = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
        recv_hash = parsed.pop("hash", None)
        if not recv_hash:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, recv_hash):
            log.warning("initData HMAC mismatch")
            return None
        age = int(time.time()) - int(parsed.get("auth_date", 0))
        if age > 3600:
            log.warning("initData expired (age=%ds)", age)
            return None
        return json.loads(parsed.get("user", "{}"))
    except Exception as e:
        log.warning("validate_init_data error: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────
# REWARD HELPER
# ──────────────────────────────────────────────────────────────────

def award_bonus(c, referrer_id: str, referred_id: str) -> bool:
    """
    Award +300 balance, +50 tickets, +1 invited to referrer.
    Returns True if bonus was newly granted.
    """
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
    if not c.fetchone():
        log.warning("REWARD REJECTED — referrer %s not in DB", referrer_id)
        return False
    try:
        c.execute(
            "INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)",
            (referrer_id, referred_id),
        )
    except sqlite3.IntegrityError:
        log.warning("REWARD REJECTED — duplicate referral_earnings referrer=%s referred=%s",
                    referrer_id, referred_id)
        return False
    c.execute(
        "UPDATE users SET balance=balance+300, tickets=tickets+50, invited=invited+1 WHERE user_id=?",
        (referrer_id,),
    )
    log.info("REWARD GRANTED — referrer=%s referred=%s +300 +50tickets +1invited +1progress",
             referrer_id, referred_id)
    log.info("PROGRESS UPDATED — referrer=%s raffle_progress+1", referrer_id)
    return True


# ──────────────────────────────────────────────────────────────────
# TELEGRAM BOT HELPERS
# ──────────────────────────────────────────────────────────────────

def tg_send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload, timeout=5
        )
    except Exception as e:
        log.error("tg_send failed: %s", e)


# ──────────────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"ok": True})

    msg = data["message"]
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "")

    if text.startswith("/start"):
        parts = text.split(None, 1)
        referrer_id = parts[1].strip() if len(parts) > 1 else None

        log.info("REFERRAL RECEIVED — user=%s referrer=%s", chat_id, referrer_id)

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
        if not c.fetchone():
            # Block self-referral
            if referrer_id == chat_id:
                log.warning("SELF-REFERRAL blocked user=%s", chat_id)
                referrer_id = None
            log.info("USER REGISTERED via bot — user=%s referrer=%s", chat_id, referrer_id)
            c.execute("INSERT INTO users (user_id, referrer_id) VALUES (?,?)",
                      (chat_id, referrer_id))
            if referrer_id:
                award_bonus(c, referrer_id, chat_id)
        else:
            log.info("user=%s already registered (bot /start)", chat_id)
        conn.commit()
        conn.close()

    base = WEBAPP_URL.rstrip("/") + "/"
    kb = {"inline_keyboard": [[{
        "text": "🚀 Открыть приложение",
        "web_app": {"url": f"{base}?ref={chat_id}"}
    }]]}
    tg_send(chat_id,
            "🌿 Добро пожаловать в Green Market!\n💰 Зарабатывай с друзьями!",
            reply_markup=kb)
    return jsonify({"ok": True})


@app.route("/api/register", methods=["POST"])
def api_register():
    """
    Register a Mini App user and award referral bonus.

    Accepts:
      { "init_data": "...", "user_id": "...", "referrer_id": "..." }

    init_data is used when available (secure). user_id fallback is used
    when opened outside Telegram (e.g. GitHub Pages direct link).
    referrer_id is always taken from the request body (stored from URL ?ref=).
    """
    body = request.get_json(silent=True) or {}

    init_data_raw = (body.get("init_data") or "").strip()
    body_user_id  = str(body.get("user_id")  or "").strip()
    referrer_id   = str(body.get("referrer_id") or "").strip() or None

    user_id = None

    if init_data_raw:
        ud = validate_init_data(init_data_raw)
        if not ud:
            return jsonify({"status": "error", "message": "invalid initData"}), 403
        user_id = str(ud.get("id", "")).strip()
        log.info("REGISTRATION STARTED (secure initData) user=%s referrer=%s", user_id, referrer_id)
    elif body_user_id:
        user_id = body_user_id
        log.info("REGISTRATION STARTED (fallback user_id) user=%s referrer=%s", user_id, referrer_id)
    else:
        return jsonify({"status": "error", "message": "no user identity"}), 400

    if not user_id:
        return jsonify({"status": "error", "message": "empty user_id"}), 400

    # Self-referral guard
    if referrer_id == user_id:
        log.warning("SELF-REFERRAL blocked — user=%s", user_id)
        referrer_id = None

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT balance, tickets, invited FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()

    if row:
        conn.close()
        log.info("user=%s already registered (Mini App)", user_id)
        return jsonify({
            "status": "already_registered",
            "bonus_awarded": False,
            "balance":  row["balance"],
            "tickets":  row["tickets"],
            "invited":  row["invited"],
        })

    c.execute("INSERT INTO users (user_id, referrer_id) VALUES (?,?)", (user_id, referrer_id))
    log.info("USER REGISTERED — user=%s referrer=%s", user_id, referrer_id)

    bonus = False
    if referrer_id:
        bonus = award_bonus(c, referrer_id, user_id)

    conn.commit()
    c.execute("SELECT balance, tickets, invited FROM users WHERE user_id=?", (user_id,))
    row2 = c.fetchone()
    conn.close()

    return jsonify({
        "status": "success",
        "bonus_awarded": bonus,
        "balance":  row2["balance"],
        "tickets":  row2["tickets"],
        "invited":  row2["invited"],
    })


@app.route("/api/stats", methods=["POST"])
def api_stats():
    """Return live stats for a user (used for polling from inviter's Mini App)."""
    body = request.get_json(silent=True) or {}
    init_data_raw = (body.get("init_data") or "").strip()
    body_user_id  = str(body.get("user_id") or "").strip()

    user_id = None
    if init_data_raw:
        ud = validate_init_data(init_data_raw)
        if not ud:
            return jsonify({"status": "error"}), 403
        user_id = str(ud.get("id", "")).strip()
    elif body_user_id:
        user_id = body_user_id
    else:
        return jsonify({"status": "error", "message": "no identity"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance, tickets, invited FROM users WHERE user_id=?", (user_id,))
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
def index():
    return "Green Market bot ✅"


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
