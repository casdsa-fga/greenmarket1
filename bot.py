from flask import Flask, request, jsonify
import requests
import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8976122112:AAGeOjA9SCOjkd_-yREBUjI55X-lrHBnmME')

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
    c.execute('''
    CREATE TABLE IF NOT EXISTS referral_earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id TEXT,
        referred_user_id TEXT,
        amount INTEGER DEFAULT 300,
        UNIQUE(referrer_id, referred_user_id)
    )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_db()

# ================= WEBHOOK =================

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"📩 Запрос: {data}")
        
        if not data or "message" not in data:
            return jsonify({"ok": True})
        
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")
        logger.info(f"💬 Сообщение от {chat_id}: {text}")
        
        referrer_id = None
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # ================= /start =================
        if text.startswith("/start"):
            parts = text.split(" ")
            if len(parts) > 1:
                referrer_id = parts[1]
                logger.info(f"👤 Реферальный ID: {referrer_id}")
            
            # Проверяем, существует ли пользователь
            c.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
            existing = c.fetchone()
            
            if not existing:
                # Создаём пользователя
                c.execute(
                    "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
                    (chat_id, referrer_id)
                )
                logger.info(f"✅ Пользователь {chat_id} зарегистрирован")
                
                # ================= НАЧИСЛЯЕМ БОНУСЫ =================
                if referrer_id and referrer_id != chat_id:
                    # Проверяем, не начисляли ли уже
                    c.execute("SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?", 
                             (referrer_id, chat_id))
                    already = c.fetchone()
                    
                    if not already:
                        c.execute("""
                            UPDATE users
                            SET balance = balance + 300,
                                tickets = tickets + 50,
                                invited = invited + 1
                            WHERE user_id = ?
                        """, (referrer_id,))
                        c.execute("INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)",
                                 (referrer_id, chat_id))
                        logger.info(f"💰 Начислено +300 ₽ пользователю {referrer_id} за {chat_id}")
            
            conn.commit()
            conn.close()
            
            # ================= КНОПКА С MINI APP =================
            keyboard = {
                "inline_keyboard": [[{
                    "text": "🚀 Открыть приложение",
                    "web_app": {
                        "url": f"https://casdsa-fga.github.io/greenmarket1/?ref={chat_id}"
                    }
                }]]
            }
            
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "🌿 Добро пожаловать в Green Market!\n💰 Зарабатывай с друзьями!",
                    "reply_markup": keyboard
                },
                timeout=10
            )
        
        return jsonify({"ok": True})
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ================= API ДЛЯ MINI APP =================

@app.route('/api/register', methods=['POST'])
def register():
    """Регистрация пользователя из Mini App"""
    try:
        data = request.get_json()
        logger.info(f"📩 Регистрация из Mini App: {data}")
        
        user_id = data.get('user_id')
        referrer_id = data.get('referrer_id')
        
        if not user_id:
            return jsonify({"status": "error", "message": "Missing user_id"}), 400
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        c.execute("SELECT user_id FROM users WHERE user_id=?", (str(user_id),))
        existing = c.fetchone()
        
        if existing:
            conn.close()
            return jsonify({"status": "success", "message": "User already registered"})
        
        if referrer_id and referrer_id != str(user_id):
            c.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (str(user_id), str(referrer_id)))
            
            c.execute("SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?", 
                     (str(referrer_id), str(user_id)))
            already = c.fetchone()
            
            if not already:
                c.execute("UPDATE users SET balance = balance + 300, tickets = tickets + 50, invited = invited + 1 WHERE user_id = ?", (str(referrer_id),))
                c.execute("INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)", (str(referrer_id), str(user_id)))
                logger.info(f"💰 Начислено +300 ₽ через API пользователю {referrer_id}")
        else:
            c.execute("INSERT INTO users (user_id) VALUES (?)", (str(user_id),))
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "User registered"})
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= HOME =================

@app.route('/')
def home():
    return "Бот работает! ✅"

@app.route('/users')
def get_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return jsonify({"users": users})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
