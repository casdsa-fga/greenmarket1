from flask import Flask, request, jsonify
import requests
import sqlite3
import logging
import os

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ===== ТОКЕН ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ИЛИ ПРЯМО =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8976122112:AAGeOjA9SCOjkd_-yREBUjI55X-lrHBnmME')

# ===== БАЗА ДАННЫХ =====
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        referrer_id TEXT,
        balance INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        invited INTEGER DEFAULT 0,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица для отслеживания начислений
    c.execute('''CREATE TABLE IF NOT EXISTS referral_earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id TEXT,
        referred_user_id TEXT,
        amount INTEGER DEFAULT 300,
        earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(referrer_id, referred_user_id)
    )''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_db()

# ============================================
# ===== ВЕБХУК (ОСНОВНОЙ) =====
# ============================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка входящих сообщений от Telegram"""
    try:
        data = request.get_json()
        logger.info(f"📩 Получен запрос: {data}")
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            logger.info(f"💬 Сообщение от {chat_id}: {text}")
            
            referrer_id = None
            
            # ===== ОБРАБОТКА /start =====
            if text.startswith('/start'):
                parts = text.split(' ')
                logger.info(f"🔍 Разбор /start: {parts}")
                
                # Проверяем, есть ли реферальный ID после /start
                if len(parts) > 1 and parts[1]:
                    referrer_id = parts[1]
                    logger.info(f"👤 Реферальный ID: {referrer_id}")
                    
                    conn = sqlite3.connect('users.db')
                    c = conn.cursor()
                    
                    # Проверяем, существует ли пользователь
                    c.execute('SELECT user_id, referrer_id FROM users WHERE user_id = ?', (str(chat_id),))
                    existing_user = c.fetchone()
                    
                    if not existing_user:
                        # ===== НОВЫЙ ПОЛЬЗОВАТЕЛЬ =====
                        # Регистрируем нового пользователя
                        c.execute('INSERT INTO users (user_id, referrer_id) VALUES (?, ?)', (str(chat_id), referrer_id))
                        logger.info(f"✅ Пользователь {chat_id} зарегистрирован с рефералом {referrer_id}")
                        
                        # ===== НАЧИСЛЯЕМ БОНУСЫ ПРИГЛАСИВШЕМУ =====
                        if referrer_id and referrer_id != str(chat_id):
                            # Проверяем, не начисляли ли уже бонус за этого пользователя
                            c.execute('SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?', 
                                     (referrer_id, str(chat_id)))
                            already_earned = c.fetchone()
                            
                            if not already_earned:
                                # Начисляем +300 ₽ и +50 тикетов пригласившему
                                c.execute('''UPDATE users 
                                           SET balance = balance + 300, 
                                               tickets = tickets + 50, 
                                               invited = invited + 1 
                                           WHERE user_id = ?''', (referrer_id,))
                                c.execute('INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)', 
                                         (referrer_id, str(chat_id)))
                                logger.info(f'💰✅ Начислено +300 ₽ и +50 тикетов пользователю {referrer_id} за приглашение {chat_id}')
                            else:
                                logger.info(f'⚠️ Бонус уже был начислен за приглашение {chat_id}')
                    else:
                        logger.info(f'⚠️ Пользователь {chat_id} уже зарегистрирован')
                        if existing_user[1]:
                            logger.info(f'ℹ️ Его реферал: {existing_user[1]}')
                    
                    conn.commit()
                    conn.close()
                else:
                    logger.info(f'ℹ️ /start без параметра (обычный запуск)')
            
            # ===== ОТПРАВКА КНОПКИ С MINI APP =====
            keyboard = {
                "inline_keyboard": [[{
                    "text": "🚀 Открыть приложение",
                    "web_app": {"url": f"https://casdsa-fga.github.io/greenmarket1/?ref={chat_id}"}
                }]]
            }
            
            # Отправляем сообщение с кнопкой
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "🌿 Добро пожаловать в Green Market!\n💰 Зарабатывай с друзьями!\n\n📱 Нажми на кнопку ниже, чтобы открыть приложение!",
                        "reply_markup": keyboard
                    },
                    timeout=10
                )
                logger.info(f"📤 Ответ Telegram: {response.status_code}")
            except requests.exceptions.Timeout:
                logger.error("❌ Таймаут при отправке сообщения в Telegram")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения: {e}")
        
        return jsonify({"status": "ok"})
    
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================
# ===== РЕГИСТРАЦИЯ ИЗ MINI APP =====
# ============================================
@app.route('/api/register', methods=['POST'])
def register():
    """Регистрация пользователя из Mini App"""
    try:
        data = request.get_json()
        logger.info(f"📩 Регистрация из Mini App: {data}")
        
        user_id = data.get('user_id')
        referrer_id = data.get('referrer_id')
        
        if not user_id:
            logger.warning("⚠️ Нет user_id")
            return jsonify({"status": "error", "message": "Missing user_id"}), 400
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # Проверяем, существует ли пользователь
        c.execute('SELECT user_id, referrer_id FROM users WHERE user_id = ?', (str(user_id),))
        existing_user = c.fetchone()
        
        if existing_user:
            conn.close()
            logger.info(f"ℹ️ Пользователь {user_id} уже зарегистрирован")
            return jsonify({"status": "success", "message": "User already registered", "user": existing_user})
        
        # Регистрируем пользователя (с рефералом, если есть)
        if referrer_id and referrer_id != str(user_id):
            c.execute('INSERT INTO users (user_id, referrer_id) VALUES (?, ?)', (str(user_id), str(referrer_id)))
            logger.info(f"✅ Пользователь {user_id} зарегистрирован через API с рефералом {referrer_id}")
            
            # Начисляем бонусы пригласившему
            c.execute('SELECT id FROM referral_earnings WHERE referrer_id = ? AND referred_user_id = ?', 
                     (str(referrer_id), str(user_id)))
            already_earned = c.fetchone()
            
            if not already_earned:
                c.execute('''UPDATE users 
                           SET balance = balance + 300, 
                               tickets = tickets + 50, 
                               invited = invited + 1 
                           WHERE user_id = ?''', (str(referrer_id),))
                c.execute('INSERT INTO referral_earnings (referrer_id, referred_user_id) VALUES (?, ?)', 
                         (str(referrer_id), str(user_id)))
                logger.info(f"💰✅ Начислено +300 ₽ и +50 тикетов пользователю {referrer_id} через API за {user_id}")
        else:
            c.execute('INSERT INTO users (user_id) VALUES (?)', (str(user_id),))
            logger.info(f"✅ Пользователь {user_id} зарегистрирован без реферала")
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "User registered"})
    
    except Exception as e:
        logger.error(f"❌ Ошибка в register: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================
# ===== ДОПОЛНИТЕЛЬНЫЕ ЭНДПОИНТЫ =====
# ============================================
@app.route('/')
def home():
    """Проверка, что бот работает"""
    return "Бот работает! ✅"

@app.route('/users')
def get_users():
    """Просмотр всех пользователей"""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users ORDER BY balance DESC')
        users = c.fetchall()
        conn.close()
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/referrals/<user_id>')
def get_referrals(user_id):
    """Просмотр рефералов пользователя"""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM referral_earnings WHERE referrer_id = ?', (user_id,))
        referrals = c.fetchall()
        conn.close()
        return jsonify({"referrals": referrals})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stats')
def get_stats():
    """Общая статистика"""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT SUM(balance) FROM users')
        total_balance = c.fetchone()[0] or 0
        c.execute('SELECT SUM(invited) FROM users')
        total_invites = c.fetchone()[0] or 0
        conn.close()
        return jsonify({
            "total_users": total_users,
            "total_balance": total_balance,
            "total_invites": total_invites
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# ===== ЗАПУСК =====
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    logger.info(f"🚀 Запуск бота на порту {port}...")
    logger.info(f"🤖 Бот: @Green_marketBot")
    logger.info(f"📱 Mini App: https://casdsa-fga.github.io/greenmarket1/")
    app.run(host='0.0.0.0', port=port, debug=False)
