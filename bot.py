from flask import Flask, request, jsonify
import sqlite3
import time

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

# ---------------- CORE ----------------
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

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
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


def process_ref(ref_id):
    if not ref_id:
        return

    conn = db()
    c = conn.cursor()

    # увеличиваем инвайты рефереру
    c.execute("SELECT * FROM users WHERE id=?", (ref_id,))
    ref_user = c.fetchone()

    if ref_user:
        c.execute("""
            UPDATE users
            SET invites = invites + 1
            WHERE id=?
        """, (ref_id,))

    conn.commit()
    conn.close()


# ---------------- TELEGRAM SIMULATION ----------------
# (сюда ты подключаешь webhook или polling)
@app.route("/start", methods=["POST"])
def start():
    data = request.json
    user_id = int(data["user_id"])
    ref = data.get("ref")

    add_user(user_id, ref)

    if ref:
        process_ref(ref)
        give_bonus(user_id)

    return {"ok": True}


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


# ---------------- SIM TEST ----------------
@app.route("/test")
def test():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
