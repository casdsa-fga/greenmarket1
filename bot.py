from flask import Flask, request, jsonify
import requests
import sqlite3
import hashlib

app = Flask(__name__)
BOT_TOKEN = "8976122112:AAGeOjA9SCOjkd_-yREBUjI55X-lrHBnmME"

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        referrer_id TEXT,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invited INTEGER DEFAULT 0,
        registered INTEGER DEFAULT 1
    )''')
    # Таблица для отслеживания уже начисленных рефералов
    c.execute('''CREATE TABLE IF NOT EXISTS referral_earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id TEXT,
        referred_user_id TEXT,
        amount INTEGER DEFAULT 300,
        UNIQUE(referrer_id, referred_user_id)
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        
        referrer_id = None
        if text.startswith('/start'):
            parts = text.split(' ')
            if len(parts) > 1:
                referrer_id = parts[1]
                
                # ===== ПРОВЕРЯЕМ, НЕ РЕГИСТРИРОВАЛСЯ ЛИ УЖЕ ЭТОТ ПОЛЬЗОВАТЕЛЬ =====
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                
                # Проверяем, существует ли пользователь
                c.execute('SELECT user_id FROM users WHERE user_id = ?', (str(chat_id),))
                existing_user = c.fetchone()
                
                if not existing_user:
                    # ===== НОВЫЙ ПОЛЬЗОВАТЕЛЬ =====
                    # Сохраняем пользователя
                    c.execute('INSERT INTO users (user_id, referrer_id) VALUES (?, ?)', (str(chat_id), referrer_id))
                    
                    # ===== НАЧИСЛЯЕМ БОНУСЫ ПРИГЛАСИВШЕМУ (ТОЛЬКО 1 РАЗ!) =====
                    if referrer_id:
                        # Проверяем, не начисляли ли уже бонусы этому рефералу за этого пользователя
                        c.execute('SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?', (referrer_id, str(chat_id)))
                        already_earned = c.fetchone()
                        
                        if not already_earned:
                            # Начисляем +300 ₽ и +50 тикетов пригласившему
                            c.execute('UPDATE users SET balance = balance + 300, tickets = tickets + 50, invited = invited + 1 WHERE user_id = ?', (referrer_id,))
                            # Записываем, что начисление уже было
                            c.execute('INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)', (referrer_id, str(chat_id)))
                            print(f'✅ Начислено +300 ₽ и +50 тикетов пользователю {referrer_id} за приглашение {chat_id}')
                        else:
                            print(f'⚠️ Бонус уже был начислен за приглашение {chat_id}')
                else:
                    print(f'⚠️ Пользователь {chat_id} уже зарегистрирован')
                
                conn.commit()
                conn.close()
        
        # ===== КНОПКА ДЛЯ ОТКРЫТИЯ MINI APP =====
        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 Открыть приложение",
                "web_app": {"url": f"https://casdsa-fga.github.io/greenmarket1/?ref={chat_id}"}
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
    
    return jsonify({"status": "ok"})

@app.route('/api/register', methods=['POST'])
def register():
    """Эндпоинт для регистрации из Mini App"""
    data = request.get_json()
    user_id = data.get('user_id')
    referrer_id = data.get('referrer_id')
    
    if not user_id or not referrer_id:
        return jsonify({"status": "error", "message": "Missing user_id or referrer_id"}), 400
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Проверяем, не зарегистрирован ли уже пользователь
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (str(user_id),))
    existing_user = c.fetchone()
    
    if existing_user:
        conn.close()
        return jsonify({"status": "error", "message": "User already registered"}), 400
    
    # Регистрируем пользователя
    c.execute('INSERT INTO users (user_id, referrer_id) VALUES (?, ?)', (str(user_id), str(referrer_id)))
    
    # Проверяем, не начисляли ли уже бонусы
    c.execute('SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?', (str(referrer_id), str(user_id)))
    already_earned = c.fetchone()
    
    if not already_earned:
        # Начисляем бонусы пригласившему
        c.execute('UPDATE users SET balance = balance + 300, tickets = tickets + 50, invited = invited + 1 WHERE user_id = ?', (str(referrer_id),))
        c.execute('INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)', (str(referrer_id), str(user_id)))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "User registered and bonus awarded"})
    else:
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "User registered, but bonus already awarded"})

@app.route('/')
def home():
    return "Бот работает! ✅"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)