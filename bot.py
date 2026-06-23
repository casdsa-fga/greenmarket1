from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)
DB = "db.sqlite3"

# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invites INTEGER DEFAULT 0,
        ref INTEGER,
        bonus_given INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

init()


# ---------------- LOGIC ----------------
def add_user(user_id, ref=None):
    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    if not user:
        c.execute("INSERT INTO users (id, ref) VALUES (?, ?)", (user_id, ref))

    conn.commit()
    conn.close()


def give_bonus(user_id):
    conn = db()
    c = conn.cursor()

    c.execute("SELECT bonus_given FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    if user and user["bonus_given"] == 0:
        c.execute("""
            UPDATE users
            SET balance = balance + 300,
                tickets = tickets + 50,
                bonus_given = 1
            WHERE id=?
        """, (user_id,))

    conn.commit()
    conn.close()


def add_invite(ref_id):
    if not ref_id:
        return

    conn = db()
    c = conn.cursor()

    c.execute("UPDATE users SET invites = invites + 1 WHERE id=?", (ref_id,))

    conn.commit()
    conn.close()


# ---------------- TELEGRAM WEBHOOK ----------------
@app.route("/", methods=["POST"])
def webhook():
    data = request.json

    print("[DEBUG] RAW:", data)

    message = data.get("message", {})
    text = message.get("text", "")
    user_id = message.get("from", {}).get("id")

    if not user_id:
        return "ok"

    print("[DEBUG] CHAT =", user_id, "TEXT =", text)

    # /start 12345
    ref = None
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            ref = parts[1]

    add_user(user_id, ref)

    if ref:
        add_invite(ref)
        give_bonus(user_id)

    return "ok"


# ---------------- API FOR HTML ----------------
@app.route("/user/<int:user_id>")
def get_user(user_id):
    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    conn.close()

    if not user:
        return jsonify({"error": "not found"})

    return jsonify({
        "id": user["id"],
        "balance": user["balance"],
        "tickets": user["tickets"],
        "invites": user["invites"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
