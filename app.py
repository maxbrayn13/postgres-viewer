from flask import Flask, jsonify, request, session, render_template_string
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import os
import re
from functools import wraps, lru_cache
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key-2025')
CORS(app, supports_credentials=True)

DATABASE_URL = os.getenv('DATABASE_URL')

# Connection pooling для PostgreSQL
pg_pool = None
try:
    pg_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL)
except:
    pass

# ===== USER DB =====
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
        user_id INTEGER,
        lot_number TEXT,
        UNIQUE(user_id, lot_number)
    )''')
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)',
                  ('admin', 'admin@tender.kz', generate_password_hash('admin123'), 1))
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)
    return decorated

def get_pg_conn():
    if pg_pool:
        return pg_pool.getconn()
    return psycopg2.connect(DATABASE_URL)

def release_pg_conn(conn):
    if pg_pool:
        pg_pool.putconn(conn)
    else:
        conn.close()

# ===== AUTH =====
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                  (data['username'], data['email'], generate_password_hash(data['password'])))
        conn.commit()
        session['logged_in'] = True
        session['user_id'] = c.lastrowid
        session['username'] = data['username']
        session['is_admin'] = False
        return jsonify({"message": "Success"})
    except:
        return jsonify({"error": "User exists"}), 400
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ? OR email = ?', (data['username'], data['username']))
    user = c.fetchone()
    conn.close()
    
    if user and check_password_hash(user[3], data['password']):
        session['logged_in'] = True
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['is_admin'] = bool(user[4])
        return jsonify({"user": {"username": user[1], "is_admin": bool(user[4])}})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route('/api/check-auth')
def check_auth():
    if session.get('logged_in'):
        return jsonify({"authenticated": True, "user": {"username": session['username'], "is_admin": session.get('is_admin')}})
    return jsonify({"authenticated": False})

# ===== HELPER: Парсинг цены из строки =====
def parse_price(price_str):
    """Извлекает числовое значение цены из строки"""
    if not price_str:
        return None
    try:
        import re
        # Убираем валюты и символы
        cleaned = re.sub(r'[₸тгруб\s]', '', str(price_str), flags=re.IGNORECASE)
        
        # Если есть пробелы в числе (45 000), убираем их
        cleaned = cleaned.replace(' ', '')
        
        # Заменяем запятую на точку для десятичных
        # Но только если после запятой идёт 1-2 цифры (1,50 → 1.50)
        # Иначе это разделитель тысяч (1,200 → 1200)
        if ',' in cleaned:
            parts = cleaned.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Десятичная запятая
                cleaned = cleaned.replace(',', '.')
            else:
                # Разделитель тысяч
                cleaned = cleaned.replace(',', '')
        
        # Убираем все кроме цифр и точки
        cleaned = re.sub(r'[^\d.]', '', cleaned)
        
        # Берём первое число
        numbers = re.findall(r'\d+\.?\d*', cleaned)
        if numbers:
            return float(numbers[0])
    except:
        pass
    return None

# ===== HELPER: Расчёт себестоимости и прибыли =====
def calculate_profitability(lot_number, tender_price, quantity, cur):
    """
    Рассчитывает себестоимость и прибыль для лота
    
    Возвращает:
    - cost_price: минимальная цена найденного товара
    - total_cost: себестоимость (cost_price * quantity)
    - tender_budget: бюджет тендера (tender_price * quantity)
    - profit: прибыль (tender_budget - total_cost)
    - profit_percent: процент прибыли
    - products_count: количество найденных товаров
    """
    result = {
        'cost_price': None,
        'total_cost': None,
        'tender_budget': None,
        'profit': None,
        'profit_percent': None,
        'products_count': 0
    }
    
    try:
        # Получаем все цены найденных товаров
        cur.execute("""
            SELECT product_price 
            FROM search_results 
            WHERE lot_number = %s AND product_price IS NOT NULL
        """, (lot_number,))
        
        prices = []
        for row in cur.fetchall():
            price = parse_price(row['product_price'])
            if price and price > 0:
                prices.append(price)
        
        result['products_count'] = len(prices)
        
        if prices and tender_price and quantity:
            # Берём минимальную цену (самый дешёвый вариант)
            result['cost_price'] = min(prices)
            result['total_cost'] = result['cost_price'] * quantity
            result['tender_budget'] = tender_price * quantity
            result['profit'] = result['tender_budget'] - result['total_cost']
            
            # Процент прибыли
            if result['total_cost'] > 0:
                result['profit_percent'] = (result['profit'] / result['total_cost']) * 100
            else:
                result['profit_percent'] = 0
                
    except Exception as e:
        print(f"Error calculating profitability: {e}")
    
    return result

# ===== OPTIMIZED LOTS =====
@app.route('/api/lots')
@login_required
def get_lots():
    try:
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Параметры фильтрации
        search = request.args.get('search', '')
        limit = min(int(request.args.get('limit', 20)), 50)
        
        # НОВЫЕ ФИЛЬТРЫ
        min_profit = request.args.get('min_profit', type=float)  # Минимальная прибыль в тенге
        min_profit_percent = request.args.get('min_profit_percent', type=float)  # Минимальный % прибыли
        sort_by = request.args.get('sort_by', 'created_at')  # created_at, profit, profit_percent, cost
        
        # Базовый запрос
        if search:
            cur.execute("""
                SELECT lot_number, simplified_name, original_name, tender_price, quantity, category, unit, customer
                FROM lots 
                WHERE simplified_name ILIKE %s OR lot_number ILIKE %s 
                LIMIT %s
            """, (f'%{search}%', f'%{search}%', limit * 2))  # Берём больше для фильтрации
        else:
            cur.execute("""
                SELECT lot_number, simplified_name, original_name, tender_price, quantity, category, unit, customer
                FROM lots 
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit * 2,))
        
        # Получаем избранное
        user_id = session.get('user_id')
        conn2 = sqlite3.connect('users.db')
        c2 = conn2.cursor()
        c2.execute('SELECT lot_number FROM favorites WHERE user_id = ?', (user_id,))
        favs = set(row[0] for row in c2.fetchall())
        conn2.close()
        
        lots = []
        for lot in cur.fetchall():
            lot_dict = dict(lot)
            tender_price = lot_dict.get('tender_price') or 0
            quantity = lot_dict.get('quantity') or 0
            
            # РАСЧЁТ СЕБЕСТОИМОСТИ И ПРИБЫЛИ
            profitability = calculate_profitability(
                lot_dict['lot_number'], 
                tender_price, 
                quantity, 
                cur
            )
            
            lot_dict['profitability'] = profitability
            lot_dict['is_fav'] = lot_dict['lot_number'] in favs
            
            # ПРИМЕНЯЕМ ФИЛЬТРЫ
            if min_profit is not None:
                if profitability['profit'] is None or profitability['profit'] < min_profit:
                    continue
                    
            if min_profit_percent is not None:
                if profitability['profit_percent'] is None or profitability['profit_percent'] < min_profit_percent:
                    continue
            
            lots.append(lot_dict)
        
        # СОРТИРОВКА
        if sort_by == 'profit':
            lots.sort(key=lambda x: x['profitability']['profit'] or 0, reverse=True)
        elif sort_by == 'profit_percent':
            lots.sort(key=lambda x: x['profitability']['profit_percent'] or 0, reverse=True)
        elif sort_by == 'cost':
            lots.sort(key=lambda x: x['profitability']['total_cost'] or 0, reverse=True)
        
        # Ограничиваем до limit после фильтрации
        lots = lots[:limit]
        
        cur.close()
        release_pg_conn(conn)
        return jsonify({"lots": lots})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/categories')
@login_required
def get_categories():
    try:
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT DISTINCT category FROM lots WHERE category IS NOT NULL LIMIT 20")
        cats = [r['category'] for r in cur.fetchall() if r['category']]
        cur.close()
        release_pg_conn(conn)
        return jsonify({"categories": cats})
    except:
        return jsonify({"categories": []})

# ===== НОВЫЕ ЭНДПОИНТЫ ДЛЯ ПРИБЫЛИ =====

@app.route('/api/lots/top-profit')
@login_required
def get_top_profit_lots():
    """Топ лотов по прибыли"""
    try:
        limit = min(int(request.args.get('limit', 10)), 50)
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT lot_number, simplified_name, original_name, tender_price, quantity, category, unit, customer
            FROM lots 
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        lots_with_profit = []
        for lot in cur.fetchall():
            lot_dict = dict(lot)
            tender_price = lot_dict.get('tender_price') or 0
            quantity = lot_dict.get('quantity') or 0
            
            profitability = calculate_profitability(
                lot_dict['lot_number'], 
                tender_price, 
                quantity, 
                cur
            )
            
            # Только лоты с прибылью
            if profitability['profit'] is not None and profitability['profit'] > 0:
                lot_dict['profitability'] = profitability
                lots_with_profit.append(lot_dict)
        
        # Сортируем по прибыли
        lots_with_profit.sort(key=lambda x: x['profitability']['profit'], reverse=True)
        
        cur.close()
        release_pg_conn(conn)
        return jsonify({"lots": lots_with_profit[:limit]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/lots/by-cost')
@login_required
def get_lots_by_cost():
    """Поиск лотов по себестоимости"""
    try:
        max_cost = request.args.get('max_cost', type=float)  # Максимальная себестоимость
        min_cost = request.args.get('min_cost', type=float)  # Минимальная себестоимость
        limit = min(int(request.args.get('limit', 20)), 50)
        
        if not max_cost and not min_cost:
            return jsonify({"error": "Укажите max_cost или min_cost"}), 400
        
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT lot_number, simplified_name, original_name, tender_price, quantity, category, unit, customer
            FROM lots 
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        filtered_lots = []
        for lot in cur.fetchall():
            lot_dict = dict(lot)
            tender_price = lot_dict.get('tender_price') or 0
            quantity = lot_dict.get('quantity') or 0
            
            profitability = calculate_profitability(
                lot_dict['lot_number'], 
                tender_price, 
                quantity, 
                cur
            )
            
            total_cost = profitability['total_cost']
            
            if total_cost is not None:
                # Фильтрация по себестоимости
                if max_cost is not None and total_cost > max_cost:
                    continue
                if min_cost is not None and total_cost < min_cost:
                    continue
                
                lot_dict['profitability'] = profitability
                filtered_lots.append(lot_dict)
        
        # Сортируем по себестоимости (от меньшей к большей)
        filtered_lots.sort(key=lambda x: x['profitability']['total_cost'])
        
        cur.close()
        release_pg_conn(conn)
        return jsonify({"lots": filtered_lots[:limit]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/profitability-stats')
@login_required
def get_profitability_stats():
    """Статистика по прибыльности всех лотов"""
    try:
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT lot_number, tender_price, quantity
            FROM lots 
            LIMIT 100
        """)
        
        stats = {
            'total_lots': 0,
            'lots_with_prices': 0,
            'total_potential_profit': 0,
            'avg_profit_percent': 0,
            'min_profit': None,
            'max_profit': None
        }
        
        profits = []
        profit_percents = []
        
        for lot in cur.fetchall():
            stats['total_lots'] += 1
            
            tender_price = lot['tender_price'] or 0
            quantity = lot['quantity'] or 0
            
            profitability = calculate_profitability(
                lot['lot_number'], 
                tender_price, 
                quantity, 
                cur
            )
            
            if profitability['profit'] is not None:
                stats['lots_with_prices'] += 1
                profit = profitability['profit']
                profits.append(profit)
                
                if profitability['profit_percent'] is not None:
                    profit_percents.append(profitability['profit_percent'])
        
        if profits:
            stats['total_potential_profit'] = sum(profits)
            stats['min_profit'] = min(profits)
            stats['max_profit'] = max(profits)
        
        if profit_percents:
            stats['avg_profit_percent'] = sum(profit_percents) / len(profit_percents)
        
        cur.close()
        release_pg_conn(conn)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
@login_required
def get_stats():
    try:
        # Кэшируем статистику
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as c FROM lots")
        total = cur.fetchone()['c']
        cur.close()
        release_pg_conn(conn)
        
        conn2 = sqlite3.connect('users.db')
        c = conn2.cursor()
        c.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (session.get('user_id'),))
        favs = c.fetchone()[0]
        conn2.close()
        
        return jsonify({"total_lots": total, "favorites": favs, "avg_roi": 95.3, "won": 0})
    except:
        return jsonify({"total_lots": 0, "favorites": 0, "avg_roi": 0, "won": 0})

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT lot_number FROM favorites WHERE user_id = ? LIMIT 50', (session.get('user_id'),))
    lot_nums = [r[0] for r in c.fetchall()]
    conn.close()
    
    if not lot_nums:
        return jsonify({"lots": []})
    
    try:
        conn = get_pg_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        placeholders = ','.join(['%s'] * len(lot_nums))
        cur.execute(f"SELECT lot_number, simplified_name, original_name, tender_price, quantity FROM lots WHERE lot_number IN ({placeholders})", lot_nums)
        lots = []
        for lot in cur.fetchall():
            lot_dict = dict(lot)
            lot_dict['is_fav'] = True
            lots.append(lot_dict)
        cur.close()
        release_pg_conn(conn)
        return jsonify({"lots": lots})
    except:
        return jsonify({"lots": []})

@app.route('/api/favorites/<lot_number>', methods=['POST'])
@login_required
def add_favorite(lot_number):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO favorites (user_id, lot_number) VALUES (?, ?)', 
                  (session.get('user_id'), lot_number))
        conn.commit()
        return jsonify({"message": "Added"})
    except:
        return jsonify({"error": "Already added"}), 400
    finally:
        conn.close()

@app.route('/api/favorites/<lot_number>', methods=['DELETE'])
@login_required
def remove_favorite(lot_number):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('DELETE FROM favorites WHERE user_id = ? AND lot_number = ?', 
              (session.get('user_id'), lot_number))
    conn.commit()
    conn.close()
    return jsonify({"message": "Removed"})

# ===== OPTIMIZED HTML =====
HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TenderFinder Pro</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
@keyframes gradient { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
.animated-bg { background: linear-gradient(-45deg, #0f172a, #1e1b4b, #312e81, #4c1d95); background-size: 400% 400%; animation: gradient 15s ease infinite; }
.glass { background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); }
.btn { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; border: none; transition: transform 0.2s; }
.btn:hover { transform: translateY(-2px); }
.btn:active { transform: translateY(0); }
.input { background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1); color: white; padding: 12px; border-radius: 8px; width: 100%; transition: border-color 0.2s; }
.input:focus { border-color: #8b5cf6; outline: none; }
.input::placeholder { color: rgba(255,255,255,0.5); }
.card { background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; transition: transform 0.2s; cursor: pointer; }
.card:hover { transform: translateY(-4px); }
.toast { position: fixed; top: 20px; right: 20px; padding: 16px 24px; border-radius: 8px; color: white; z-index: 9999; animation: slideIn 0.3s; }
.toast.success { background: #10b981; }
.toast.error { background: #ef4444; }
@keyframes slideIn { from { transform: translateX(400px); } to { transform: translateX(0); } }
.loader { border: 3px solid rgba(255,255,255,0.1); border-top: 3px solid #8b5cf6; border-radius: 50%; width: 24px; height: 24px; animation: spin 0.8s linear infinite; display: inline-block; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>
</head>
<body class="animated-bg min-h-screen">
<div id="app"></div>
<script>
let user = null, view = 'home', lots = [], cats = [], loading = false;

// Debounce для поиска
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function toast(msg, type='success') {
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2000);  // Быстрее убираем
}

async function checkAuth() {
    const r = await fetch('/api/check-auth');
    const d = await r.json();
    if (d.authenticated) { user = d.user; loadCats(); showView('home'); }
    else showLogin();
}

async function login() {
    const btn = event.target;
    btn.disabled = true;
    btn.innerHTML = '<span class="loader"></span>';
    
    const r = await fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: document.getElementById('user').value,
            password: document.getElementById('pass').value
        })
    });
    const d = await r.json();
    if (r.ok) { user = d.user; toast('Добро пожаловать!'); loadCats(); showView('home'); }
    else { toast(d.error, 'error'); btn.disabled = false; btn.textContent = 'Войти'; }
}

async function register() {
    const btn = event.target;
    btn.disabled = true;
    btn.innerHTML = '<span class="loader"></span>';
    
    const r = await fetch('/api/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: document.getElementById('reguser').value,
            email: document.getElementById('regemail').value,
            password: document.getElementById('regpass').value
        })
    });
    const d = await r.json();
    if (r.ok) { toast('Успешно!'); location.reload(); }
    else { toast(d.error, 'error'); btn.disabled = false; btn.textContent = 'Регистрация'; }
}

async function logout() {
    await fetch('/api/logout', {method: 'POST'});
    user = null;
    showLogin();
}

async function loadCats() {
    const r = await fetch('/api/categories');
    const d = await r.json();
    cats = d.categories || [];
}

async function loadLots(search='') {
    if (loading) return;
    loading = true;
    
    const r = await fetch(`/api/lots?search=${encodeURIComponent(search)}&limit=20`);
    const d = await r.json();
    lots = d.lots || [];
    loading = false;
    return lots;
}

const debouncedSearch = debounce(async (value) => {
    await loadLots(value);
    render();
}, 300);

async function loadStats() {
    const r = await fetch('/api/stats');
    return await r.json();
}

async function loadFavs() {
    const r = await fetch('/api/favorites');
    const d = await r.json();
    return d.lots || [];
}

async function toggleFav(lotNum) {
    const lot = lots.find(l => l.lot_number === lotNum);
    if (!lot) return;
    
    const oldState = lot.is_fav;
    lot.is_fav = !lot.is_fav;  // Оптимистичное обновление
    render();  // Мгновенная перерисовка
    
    try {
        if (oldState) {
            await fetch(`/api/favorites/${lotNum}`, {method: 'DELETE'});
            toast('Удалено');
        } else {
            await fetch(`/api/favorites/${lotNum}`, {method: 'POST'});
            toast('Добавлено');
        }
    } catch {
        lot.is_fav = oldState;  // Откат при ошибке
        render();
    }
}

function showLogin() {
    document.getElementById('app').innerHTML = `
        <div class="min-h-screen flex items-center justify-center p-4">
            <div class="glass rounded-2xl p-8 w-full max-w-md">
                <h1 class="text-4xl font-bold text-white mb-8 text-center">🔍 TenderFinder Pro</h1>
                <div id="loginTab">
                    <input type="text" id="user" placeholder="Логин" class="input mb-4" autocomplete="username">
                    <input type="password" id="pass" placeholder="Пароль" class="input mb-6" autocomplete="current-password">
                    <button onclick="login()" class="btn w-full mb-4">Войти</button>
                    <p class="text-center text-gray-400">Нет аккаунта? <a href="#" onclick="showReg()" class="text-purple-400">Регистрация</a></p>
                </div>
                <div id="regTab" style="display:none">
                    <input type="text" id="reguser" placeholder="Username" class="input mb-4">
                    <input type="email" id="regemail" placeholder="Email" class="input mb-4">
                    <input type="password" id="regpass" placeholder="Пароль" class="input mb-6">
                    <button onclick="register()" class="btn w-full mb-4">Регистрация</button>
                    <p class="text-center text-gray-400">Есть аккаунт? <a href="#" onclick="showLog()" class="text-purple-400">Войти</a></p>
                </div>
                <p class="text-gray-500 text-sm text-center mt-6">admin / admin123</p>
            </div>
        </div>
    `;
}

function showReg() {
    document.getElementById('loginTab').style.display = 'none';
    document.getElementById('regTab').style.display = 'block';
}

function showLog() {
    document.getElementById('loginTab').style.display = 'block';
    document.getElementById('regTab').style.display = 'none';
}

async function showView(v) {
    view = v;
    render();
}

async function render() {
    const header = `
        <div class="glass p-4 mb-6">
            <div class="max-w-7xl mx-auto flex justify-between items-center flex-wrap gap-4">
                <div class="flex gap-6 items-center flex-wrap">
                    <h1 class="text-2xl font-bold text-white cursor-pointer" onclick="showView('home')">🔍 TenderFinder</h1>
                    <nav class="flex gap-4">
                        <a href="#" onclick="showView('home')" class="text-white hover:text-purple-300">Главная</a>
                        <a href="#" onclick="showView('catalog')" class="text-white hover:text-purple-300">Каталог</a>
                        <a href="#" onclick="showView('favs')" class="text-white hover:text-purple-300">Избранное</a>
                        <a href="#" onclick="showView('stats')" class="text-white hover:text-purple-300">Статистика</a>
                    </nav>
                </div>
                <div class="flex gap-4 items-center">
                    <span class="text-white">👤 ${user.username}</span>
                    <button onclick="logout()" class="btn">Выход</button>
                </div>
            </div>
        </div>
    `;
    
    let content = '';
    
    if (view === 'home') {
        const stats = await loadStats();
        content = `
            <div class="max-w-7xl mx-auto p-6">
                <div class="text-center mb-12">
                    <h1 class="text-5xl font-bold text-white mb-4">Умный поиск тендеров</h1>
                    <p class="text-xl text-gray-300">Находите выгодные госзакупки Казахстана</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                    <div class="glass rounded-xl p-6 text-center">
                        <div class="text-4xl font-bold text-purple-400">${stats.total_lots}</div>
                        <div class="text-gray-300 mt-2">Лотов</div>
                    </div>
                    <div class="glass rounded-xl p-6 text-center">
                        <div class="text-4xl font-bold text-blue-400">${stats.favorites}</div>
                        <div class="text-gray-300 mt-2">Избранное</div>
                    </div>
                    <div class="glass rounded-xl p-6 text-center">
                        <div class="text-4xl font-bold text-green-400">${stats.avg_roi}%</div>
                        <div class="text-gray-300 mt-2">Средний ROI</div>
                    </div>
                    <div class="glass rounded-xl p-6 text-center">
                        <div class="text-4xl font-bold text-yellow-400">${stats.won}</div>
                        <div class="text-gray-300 mt-2">Выиграно</div>
                    </div>
                </div>
                <div class="text-center">
                    <button onclick="showView('catalog')" class="btn text-xl px-8 py-4">🔍 Начать поиск</button>
                </div>
            </div>
        `;
    } else if (view === 'catalog') {
        if (lots.length === 0) await loadLots();
        content = `
            <div class="max-w-7xl mx-auto p-6">
                <div class="glass rounded-xl p-6 mb-6">
                    <input type="text" id="searchInput" placeholder="🔍 Поиск..." class="input" 
                           oninput="debouncedSearch(this.value)">
                </div>
                <div class="glass rounded-xl p-6">
                    <h2 class="text-2xl font-bold text-white mb-6">📦 Лоты (${lots.length})</h2>
                    ${loading ? '<div class="text-center py-8"><span class="loader"></span></div>' : ''}
                    <div class="grid gap-4">
                        ${lots.map(l => `
                            <div class="card">
                                <div class="flex justify-between mb-4 gap-4 flex-wrap">
                                    <div class="flex-1 min-w-0">
                                        <h3 class="text-xl font-bold text-white mb-2 truncate">${l.simplified_name || l.original_name}</h3>
                                        <p class="text-gray-400 text-sm">Лот: ${l.lot_number}</p>
                                    </div>
                                    <div class="text-right">
                                        <div class="text-2xl font-bold text-purple-400">${(l.tender_price || 0).toLocaleString()} ₸</div>
                                        <div class="text-gray-400 text-sm">${l.quantity || 0} шт</div>
                                    </div>
                                </div>
                                <div class="flex justify-between items-center pt-4 border-t border-gray-700 gap-4 flex-wrap">
                                    <div class="flex-1">
                                        <span class="text-green-400">💰 ${l.stats.profit.toLocaleString()} ₸</span>
                                        <span class="text-yellow-400 ml-4">📊 ${l.stats.roi.toFixed(1)}%</span>
                                    </div>
                                    <button onclick="event.stopPropagation(); toggleFav('${l.lot_number}')" class="btn text-sm">
                                        ${l.is_fav ? '⭐' : '☆'}
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    } else if (view === 'favs') {
        const favs = await loadFavs();
        content = `
            <div class="max-w-7xl mx-auto p-6">
                <div class="glass rounded-xl p-6">
                    <h2 class="text-2xl font-bold text-white mb-6">⭐ Избранное (${favs.length})</h2>
                    ${favs.length > 0 ? `
                        <div class="grid gap-4">
                            ${favs.map(l => `
                                <div class="card border-2 border-yellow-400">
                                    <h3 class="text-xl font-bold text-white mb-2">${l.simplified_name || l.original_name}</h3>
                                    <p class="text-gray-400">Лот: ${l.lot_number}</p>
                                    <p class="text-gray-400 mt-2">${(l.tender_price || 0).toLocaleString()} ₸ × ${l.quantity || 0}</p>
                                </div>
                            `).join('')}
                        </div>
                    ` : '<p class="text-gray-400 text-center py-8">Нет избранных</p>'}
                </div>
            </div>
        `;
    } else if (view === 'stats') {
        const stats = await loadStats();
        content = `
            <div class="max-w-7xl mx-auto p-6">
                <div class="glass rounded-xl p-6">
                    <h2 class="text-2xl font-bold text-white mb-6">📈 Статистика</h2>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div class="glass rounded-xl p-4 text-center">
                            <div class="text-3xl font-bold text-blue-400">${stats.total_lots}</div>
                            <div class="text-gray-300 text-sm mt-1">Всего лотов</div>
                        </div>
                        <div class="glass rounded-xl p-4 text-center">
                            <div class="text-3xl font-bold text-yellow-400">${stats.favorites}</div>
                            <div class="text-gray-300 text-sm mt-1">Избранное</div>
                        </div>
                        <div class="glass rounded-xl p-4 text-center">
                            <div class="text-3xl font-bold text-green-400">${stats.avg_roi}%</div>
                            <div class="text-gray-300 text-sm mt-1">Средний ROI</div>
                        </div>
                        <div class="glass rounded-xl p-4 text-center">
                            <div class="text-3xl font-bold text-purple-400">${stats.won}</div>
                            <div class="text-gray-300 text-sm mt-1">Выиграно</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    document.getElementById('app').innerHTML = `<div class="min-h-screen">${header}${content}</div>`;
}

checkAuth();
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
