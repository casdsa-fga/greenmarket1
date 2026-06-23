from flask import Flask, request, jsonify
import requests
import sqlite3

app = Flask(__name__)

BOT_TOKEN = "YOUR_NEW_TOKEN_HERE"

# ================= DB =================

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        referrer_id TEXT,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invited INTEGER DEFAULT 0
    )
    ''')

    conn.commit()
    conn.close()

init_db()

# ================= WEBHOOK =================

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"ok": True})

    msg = data["message"]
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "")

    referrer_id = None

    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    # ================= /start =================
    if text.startswith("/start"):

        parts = text.split(" ")
        if len(parts) > 1:
            referrer_id = parts[1]

        # создаём пользователя
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)",
            (chat_id, referrer_id)
        )

        # ================= реферал =================
        if referrer_id and referrer_id != chat_id:

            c.execute("SELECT user_id FROM users WHERE user_id=?", (referrer_id,))
            exists = c.fetchone()

            if exists:
                c.execute("""
                    UPDATE users
                    SET balance = balance + 300,
                        tickets = tickets + 50,
                        invited = invited + 1
                    WHERE user_id = ?
                """, (referrer_id,))

        conn.commit()
        conn.close()

        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 Открыть приложение",
                "web_app": {
                    "url": "https://casdsa-fga.github.io/greenmarket1/"
                }
            }]]
        }

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "🌿 Добро пожаловать в Green Market!\n💰 Зарабатывай с друзьями!",
                "reply_markup": keyboard
            }
        )

    return jsonify({"ok": True})


# ================= HOME =================

@app.route('/')
def home():
    return "Бот работает! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
