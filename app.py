from flask import Flask, jsonify, request, session, render_template_string
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from functools import wraps
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'tenderfinder-secret-2025')
CORS(app, supports_credentials=True)

DATABASE_URL = os.getenv('DATABASE_URL')
USERS_DB = 'users.db'

# ============= DATABASE INITIALIZATION =============

def init_users_db():
    """Инициализация базы пользователей"""
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        hashed = generate_password_hash('admin123')
        cursor.execute(
            'INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)',
            ('admin', 'admin@tender.kz', hashed, 1)
        )
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_number TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, lot_number)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_number TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, lot_number)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_number TEXT NOT NULL,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS won_tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_number TEXT NOT NULL,
            actual_profit REAL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, lot_number)
        )
    ''')
    
    conn.commit()
    conn.close()

init_users_db()

# ============= DECORATORS =============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or not session.get('is_admin'):
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============= DATABASE HELPERS =============

def get_users_db():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_pg_db():
    return psycopg2.connect(DATABASE_URL)

def calculate_stats(lot):
    """Быстрый расчёт статистики"""
    price = lot.get('tender_price') or 0
    qty = lot.get('quantity') or 0
    
    best_price = price * 0.4
    total_cost = best_price * qty
    delivery = total_cost * 0.15
    total_expense = total_cost + delivery
    revenue = price * qty
    profit = revenue - total_expense
    profit_margin = (profit / revenue * 100) if revenue > 0 else 0
    roi = (profit / total_expense * 100) if total_expense > 0 else 0
    
    return {
        'best_price': round(best_price, 2),
        'total_cost': round(total_cost, 2),
        'delivery_cost': round(delivery, 2),
        'total_expense': round(total_expense, 2),
        'revenue': round(revenue, 2),
        'profit': round(profit, 2),
        'profit_margin': round(profit_margin, 2),
        'roi': round(roi, 2)
    }

# ============= AUTH API =============

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({"error": "All fields required"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    conn = get_users_db()
    cursor = conn.cursor()
    
    try:
        hashed = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
            (username, email, hashed)
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        session['logged_in'] = True
        session['user_id'] = user_id
        session['username'] = username
        session['is_admin'] = False
        
        conn.close()
        return jsonify({
            "message": "Registration successful",
            "user": {"id": user_id, "username": username, "email": email, "is_admin": False}
        })
    except:
        conn.close()
        return jsonify({"error": "Username or email already exists"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    conn = get_users_db()
    user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, username)).fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    session['logged_in'] = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['is_admin'] = bool(user['is_admin'])
    
    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "is_admin": bool(user['is_admin'])
        }
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route('/api/check-auth')
def check_auth():
    if session.get('logged_in'):
        return jsonify({
            "authenticated": True,
            "user": {
                "id": session.get('user_id'),
                "username": session.get('username'),
                "is_admin": session.get('is_admin', False)
            }
        })
    return jsonify({"authenticated": False})

# ============= LOTS API =============

@app.route('/api/lots')
@login_required
def get_lots():
    """Оптимизированная загрузка с пагинацией"""
    try:
        search = request.args.get('search', '')
        category = request.args.get('category', '')
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = int(request.args.get('offset', 0))
        min_roi = request.args.get('min_roi', '')
        max_roi = request.args.get('max_roi', '')
        min_budget = request.args.get('min_budget', '')
        max_budget = request.args.get('max_budget', '')
        
        user_id = session.get('user_id')
        
        conn = get_pg_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM lots WHERE 1=1"
        params = []
        
        if search:
            query += " AND (simplified_name ILIKE %s OR original_name ILIKE %s OR lot_number ILIKE %s)"
            term = f"%{search}%"
            params.extend([term, term, term])
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        lots = cursor.fetchall()
        
        lot_numbers = [lot['lot_number'] for lot in lots]
        
        conn_user = get_users_db()
        placeholders = ','.join(['?'] * len(lot_numbers))
        
        favorites = set()
        notes_dict = {}
        views_set = set()
        won_set = set()
        
        if lot_numbers:
            fav_query = f"SELECT lot_number FROM favorites WHERE user_id = ? AND lot_number IN ({placeholders})"
            favorites = set(row[0] for row in conn_user.execute(fav_query, [user_id] + lot_numbers))
            
            notes_query = f"SELECT lot_number, note FROM notes WHERE user_id = ? AND lot_number IN ({placeholders})"
            notes_dict = {row[0]: row[1] for row in conn_user.execute(notes_query, [user_id] + lot_numbers)}
            
            views_query = f"SELECT DISTINCT lot_number FROM views WHERE user_id = ? AND lot_number IN ({placeholders})"
            views_set = set(row[0] for row in conn_user.execute(views_query, [user_id] + lot_numbers))
            
            won_query = f"SELECT lot_number FROM won_tenders WHERE user_id = ? AND lot_number IN ({placeholders})"
            won_set = set(row[0] for row in conn_user.execute(won_query, [user_id] + lot_numbers))
        
        conn_user.close()
        
        result = []
        for lot in lots:
            lot_dict = dict(lot)
            stats = calculate_stats(lot)
            lot_dict['stats'] = stats
            lot_dict['is_favorite'] = lot['lot_number'] in favorites
            lot_dict['has_note'] = lot['lot_number'] in notes_dict
            lot_dict['note'] = notes_dict.get(lot['lot_number'])
            lot_dict['is_viewed'] = lot['lot_number'] in views_set
            lot_dict['is_won'] = lot['lot_number'] in won_set
            
            # Фильтры
            if min_roi and stats['roi'] < float(min_roi):
                continue
            if max_roi and stats['roi'] > float(max_roi):
                continue
            if min_budget and stats['total_expense'] < float(min_budget):
                continue
            if max_budget and stats['total_expense'] > float(max_budget):
                continue
                
            result.append(lot_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify({"lots": result})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/lots/<lot_number>')
@login_required
def get_lot_detail(lot_number):
    try:
        user_id = session.get('user_id')
        
        conn = get_pg_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM lots WHERE lot_number = %s", [lot_number])
        lot = cursor.fetchone()
        
        if not lot:
            return jsonify({"error": "Lot not found"}), 404
        
        conn_user = get_users_db()
        conn_user.execute('INSERT INTO views (user_id, lot_number) VALUES (?, ?)', (user_id, lot_number))
        conn_user.commit()
        conn_user.close()
        
        lot_dict = dict(lot)
        lot_dict['stats'] = calculate_stats(lot)
        
        cursor.close()
        conn.close()
        
        return jsonify(lot_dict)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/categories')
@login_required  
def get_categories():
    try:
        conn = get_pg_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT DISTINCT category FROM lots WHERE category IS NOT NULL AND category != ''")
        categories = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"categories": [c['category'] for c in categories]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============= FAVORITES API =============

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    user_id = session.get('user_id')
    
    conn_user = get_users_db()
    lot_numbers = [row[0] for row in conn_user.execute(
        'SELECT lot_number FROM favorites WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    )]
    conn_user.close()
    
    if not lot_numbers:
        return jsonify({"lots": []})
    
    conn = get_pg_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    placeholders = ','.join(['%s'] * len(lot_numbers))
    cursor.execute(f"SELECT * FROM lots WHERE lot_number IN ({placeholders})", lot_numbers)
    lots = cursor.fetchall()
    cursor.close()
    conn.close()
    
    result = []
    for lot in lots:
        lot_dict = dict(lot)
        lot_dict['stats'] = calculate_stats(lot)
        lot_dict['is_favorite'] = True
        result.append(lot_dict)
    
    return jsonify({"lots": result})

@app.route('/api/favorites/<lot_number>', methods=['POST'])
@login_required
def add_favorite(lot_number):
    user_id = session.get('user_id')
    conn = get_users_db()
    try:
        conn.execute('INSERT INTO favorites (user_id, lot_number) VALUES (?, ?)', (user_id, lot_number))
        conn.commit()
        conn.close()
        return jsonify({"message": "Added to favorites"})
    except:
        conn.close()
        return jsonify({"message": "Already in favorites"}), 400

@app.route('/api/favorites/<lot_number>', methods=['DELETE'])
@login_required
def remove_favorite(lot_number):
    user_id = session.get('user_id')
    conn = get_users_db()
    conn.execute('DELETE FROM favorites WHERE user_id = ? AND lot_number = ?', (user_id, lot_number))
    conn.commit()
    conn.close()
    return jsonify({"message": "Removed from favorites"})

# ============= NOTES API =============

@app.route('/api/notes/<lot_number>', methods=['GET'])
@login_required
def get_note(lot_number):
    user_id = session.get('user_id')
    conn = get_users_db()
    note = conn.execute('SELECT note FROM notes WHERE user_id = ? AND lot_number = ?', (user_id, lot_number)).fetchone()
    conn.close()
    
    if note:
        return jsonify({"note": note[0]})
    return jsonify({"note": None})

@app.route('/api/notes/<lot_number>', methods=['POST'])
@login_required
def save_note(lot_number):
    user_id = session.get('user_id')
    data = request.get_json()
    note_text = data.get('note', '')
    
    conn = get_users_db()
    conn.execute(
        'INSERT OR REPLACE INTO notes (user_id, lot_number, note, updated_at) VALUES (?, ?, ?, ?)',
        (user_id, lot_number, note_text, datetime.now())
    )
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Note saved"})

@app.route('/api/notes/<lot_number>', methods=['DELETE'])
@login_required
def delete_note(lot_number):
    user_id = session.get('user_id')
    conn = get_users_db()
    conn.execute('DELETE FROM notes WHERE user_id = ? AND lot_number = ?', (user_id, lot_number))
    conn.commit()
    conn.close()
    return jsonify({"message": "Note deleted"})

# ============= STATS API =============

@app.route('/api/stats')
@login_required
def get_stats():
    user_id = session.get('user_id')
    
    conn_pg = get_pg_db()
    cursor = conn_pg.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT COUNT(*) as count FROM lots")
    total_lots = cursor.fetchone()['count']
    
    conn_user = get_users_db()
    
    viewed = conn_user.execute('SELECT COUNT(DISTINCT lot_number) FROM views WHERE user_id = ?', (user_id,)).fetchone()[0]
    favorites = conn_user.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (user_id,)).fetchone()[0]
    notes = conn_user.execute('SELECT COUNT(*) FROM notes WHERE user_id = ?', (user_id,)).fetchone()[0]
    won = conn_user.execute('SELECT COUNT(*) FROM won_tenders WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    fav_lots = [row[0] for row in conn_user.execute('SELECT lot_number FROM favorites WHERE user_id = ?', (user_id,))]
    
    total_profit = 0
    avg_roi = 0
    if fav_lots:
        placeholders = ','.join(['%s'] * len(fav_lots))
        cursor.execute(f"SELECT * FROM lots WHERE lot_number IN ({placeholders})", fav_lots)
        roi_sum = 0
        count = 0
        for lot in cursor.fetchall():
            stats = calculate_stats(dict(lot))
            total_profit += stats['profit']
            roi_sum += stats['roi']
            count += 1
        avg_roi = roi_sum / count if count > 0 else 0
    
    conn_user.close()
    cursor.close()
    conn_pg.close()
    
    return jsonify({
        "total_lots": total_lots,
        "viewed": viewed,
        "favorites": favorites,
        "notes": notes,
        "won": won,
        "total_profit": round(total_profit, 2),
        "avg_roi": round(avg_roi, 2),
        "win_rate": round((won / viewed * 100) if viewed > 0 else 0, 2)
    })

# ============= WON TENDERS API =============

@app.route('/api/won/<lot_number>', methods=['POST'])
@login_required
def mark_won(lot_number):
    user_id = session.get('user_id')
    data = request.get_json()
    actual_profit = data.get('actual_profit', 0)
    comment = data.get('comment', '')
    
    conn = get_users_db()
    conn.execute(
        'INSERT OR REPLACE INTO won_tenders (user_id, lot_number, actual_profit, comment) VALUES (?, ?, ?, ?)',
        (user_id, lot_number, actual_profit, comment)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Marked as won"})

@app.route('/api/won', methods=['GET'])
@login_required
def get_won():
    user_id = session.get('user_id')
    
    conn = get_users_db()
    won_list = conn.execute(
        'SELECT * FROM won_tenders WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    
    return jsonify({"won": [dict(row) for row in won_list]})

# ============= ADMIN API =============

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    conn = get_users_db()
    users = conn.execute('SELECT id, username, email, is_admin, created_at FROM users').fetchall()
    conn.close()
    
    return jsonify({"users": [dict(u) for u in users]})

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def admin_update_user(user_id):
    data = request.get_json()
    is_admin = data.get('is_admin', 0)
    
    conn = get_users_db()
    conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (is_admin, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "User updated"})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({"error": "Cannot delete yourself"}), 400
    
    conn = get_users_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "User deleted"})

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TenderFinder Pro - Умный поиск тендеров</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        @keyframes gradient-x {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .animated-bg {
            background: linear-gradient(-45deg, #0f172a, #1e1b4b, #312e81, #4c1d95);
            background-size: 400% 400%;
            animation: gradient-x 15s ease infinite;
        }
        .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); }
        .glass-strong { background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(30px); border: 1px solid rgba(255, 255, 255, 0.2); }
        .card-hover { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-hover:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(139, 92, 246, 0.3); }
        .btn-primary { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); transition: all 0.3s; border: none; color: white; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; }
        .btn-primary:hover { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); transform: translateY(-2px); box-shadow: 0 10px 30px rgba(139, 92, 246, 0.4); }
        .input-modern { background: rgba(255, 255, 255, 0.05); border: 2px solid rgba(255, 255, 255, 0.1); color: white; padding: 12px; border-radius: 8px; transition: all 0.3s; width: 100%; }
        .input-modern:focus { background: rgba(255, 255, 255, 0.08); border-color: #8b5cf6; box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.1); outline: none; }
        .input-modern::placeholder { color: rgba(255, 255, 255, 0.5); }
        .badge { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
        .badge-admin { background: linear-gradient(135deg, #fbbf24, #f59e0b); color: #78350f; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-content { background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); border-radius: 16px; padding: 32px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; }
        .toast { position: fixed; top: 20px; right: 20px; padding: 16px 24px; border-radius: 8px; color: white; z-index: 2000; animation: slideIn 0.3s ease; }
        .toast-success { background: #10b981; }
        .toast-error { background: #ef4444; }
        @keyframes slideIn { from { transform: translateX(400px); } to { transform: translateX(0); } }
    </style>
</head>
<body class="animated-bg min-h-screen">
    <div id="app"></div>
    
    <script>
        let currentUser = null;
        let currentView = 'home';
        let lots = [];
        let categories = [];
        let filters = { search: '', category: '', minRoi: '', maxRoi: '', minBudget: '', maxBudget: '' };
        
        // ===== TOAST =====
        function showToast(message, type='success') {
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        // ===== AUTH =====
        async function checkAuth() {
            const res = await fetch('/api/check-auth');
            const data = await res.json();
            if (data.authenticated) {
                currentUser = data.user;
                loadCategories();
                showView('home');
            } else {
                showLogin();
            }
        }
        
        async function login() {
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            
            const data = await res.json();
            if (res.ok) {
                currentUser = data.user;
                showToast('Добро пожаловать!');
                loadCategories();
                showView('home');
            } else {
                showToast(data.error, 'error');
            }
        }
        
        async function register() {
            const username = document.getElementById('reg_username').value;
            const email = document.getElementById('reg_email').value;
            const password = document.getElementById('reg_password').value;
            
            const res = await fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, email, password})
            });
            
            const data = await res.json();
            if (res.ok) {
                currentUser = data.user;
                showToast('Регистрация успешна!');
                loadCategories();
                showView('home');
            } else {
                showToast(data.error, 'error');
            }
        }
        
        async function logout() {
            await fetch('/api/logout', {method: 'POST'});
            currentUser = null;
            showLogin();
            showToast('Вы вышли из системы');
        }
        
        // ===== DATA LOADING =====
        async function loadCategories() {
            const res = await fetch('/api/categories');
            const data = await res.json();
            categories = data.categories || [];
        }
        
        async function loadLots() {
            const params = new URLSearchParams({
                search: filters.search,
                category: filters.category,
                min_roi: filters.minRoi,
                max_roi: filters.maxRoi,
                min_budget: filters.minBudget,
                max_budget: filters.maxBudget,
                limit: 50
            });
            
            const res = await fetch(`/api/lots?${params}`);
            const data = await res.json();
            lots = data.lots || [];
            return lots;
        }
        
        async function loadStats() {
            const res = await fetch('/api/stats');
            return await res.json();
        }
        
        async function loadFavorites() {
            const res = await fetch('/api/favorites');
            const data = await res.json();
            return data.lots || [];
        }
        
        async function toggleFavorite(lotNumber) {
            const lot = lots.find(l => l.lot_number === lotNumber);
            if (lot && lot.is_favorite) {
                await fetch(`/api/favorites/${lotNumber}`, {method: 'DELETE'});
                lot.is_favorite = false;
                showToast('Удалено из избранного');
            } else if (lot) {
                await fetch(`/api/favorites/${lotNumber}`, {method: 'POST'});
                lot.is_favorite = true;
                showToast('Добавлено в избранное');
            }
            renderCurrentView();
        }
        
        // ===== VIEWS =====
        function showLogin() {
            document.getElementById('app').innerHTML = `
                <div class="min-h-screen flex items-center justify-center p-4">
                    <div class="glass-strong rounded-2xl p-8 w-full max-w-md">
                        <h1 class="text-4xl font-bold text-white mb-2 text-center">🔍 TenderFinder Pro</h1>
                        <p class="text-gray-300 text-center mb-8">Умный поиск тендеров</p>
                        
                        <div id="loginTab">
                            <input type="text" id="username" placeholder="Email или логин" class="input-modern mb-4">
                            <input type="password" id="password" placeholder="Пароль" class="input-modern mb-6">
                            <button onclick="login()" class="btn-primary w-full mb-4">Войти</button>
                            <p class="text-center text-gray-400">Нет аккаунта? <a href="#" onclick="showRegisterTab()" class="text-purple-400">Регистрация</a></p>
                        </div>
                        
                        <div id="registerTab" style="display:none;">
                            <input type="text" id="reg_username" placeholder="Имя пользователя" class="input-modern mb-4">
                            <input type="email" id="reg_email" placeholder="Email" class="input-modern mb-4">
                            <input type="password" id="reg_password" placeholder="Пароль (мин. 6 символов)" class="input-modern mb-6">
                            <button onclick="register()" class="btn-primary w-full mb-4">Зарегистрироваться</button>
                            <p class="text-center text-gray-400">Уже есть аккаунт? <a href="#" onclick="showLoginTab()" class="text-purple-400">Войти</a></p>
                        </div>
                        
                        <p class="text-gray-400 text-sm text-center mt-6">По умолчанию: admin / admin123</p>
                    </div>
                </div>
            `;
        }
        
        function showLoginTab() {
            document.getElementById('loginTab').style.display = 'block';
            document.getElementById('registerTab').style.display = 'none';
        }
        
        function showRegisterTab() {
            document.getElementById('loginTab').style.display = 'none';
            document.getElementById('registerTab').style.display = 'block';
        }
        
        async function showView(view) {
            currentView = view;
            renderCurrentView();
        }
        
        async function renderCurrentView() {
            const header = `
                <div class="glass-strong p-4 mb-6">
                    <div class="max-w-7xl mx-auto flex justify-between items-center">
                        <div class="flex items-center gap-6">
                            <h1 class="text-2xl font-bold text-white cursor-pointer" onclick="showView('home')">🔍 TenderFinder Pro</h1>
                            <nav class="flex gap-4">
                                <a href="#" onclick="showView('home')" class="text-white hover:text-purple-300">🏠 Главная</a>
                                <a href="#" onclick="showView('catalog')" class="text-white hover:text-purple-300">📊 Каталог</a>
                                <a href="#" onclick="showView('favorites')" class="text-white hover:text-purple-300">⭐ Избранное</a>
                                <a href="#" onclick="showView('stats')" class="text-white hover:text-purple-300">📈 Статистика</a>
                                ${currentUser.is_admin ? '<a href="#" onclick="showView(\'admin\')" class="text-white hover:text-purple-300">⚙️ Админка</a>' : ''}
                            </nav>
                        </div>
                        <div class="flex items-center gap-4">
                            <span class="text-white">👤 ${currentUser.username} ${currentUser.is_admin ? '<span class="badge badge-admin">ADMIN</span>' : ''}</span>
                            <button onclick="logout()" class="btn-primary">Выход</button>
                        </div>
                    </div>
                </div>
            `;
            
            let content = '';
            
            if (currentView === 'home') {
                const stats = await loadStats();
                content = `
                    <div class="max-w-7xl mx-auto p-6">
                        <div class="text-center mb-12">
                            <h1 class="text-5xl font-bold text-white mb-4">Умный поиск тендеров Казахстана</h1>
                            <p class="text-xl text-gray-300">Находите выгодные госзакупки с максимальной прибылью</p>
                        </div>
                        
                        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-4xl font-bold text-purple-400">${stats.total_lots}</div>
                                <div class="text-gray-300 mt-2">Всего лотов</div>
                            </div>
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-4xl font-bold text-blue-400">${stats.favorites}</div>
                                <div class="text-gray-300 mt-2">В избранном</div>
                            </div>
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-4xl font-bold text-green-400">${stats.avg_roi.toFixed(1)}%</div>
                                <div class="text-gray-300 mt-2">Средний ROI</div>
                            </div>
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-4xl font-bold text-yellow-400">${stats.won}</div>
                                <div class="text-gray-300 mt-2">Выиграно</div>
                            </div>
                        </div>
                        
                        <div class="text-center">
                            <button onclick="showView('catalog')" class="btn-primary text-xl px-8 py-4">🔍 Начать поиск</button>
                        </div>
                    </div>
                `;
            } else if (currentView === 'catalog') {
                await loadLots();
                content = `
                    <div class="max-w-7xl mx-auto p-6">
                        <div class="glass-strong rounded-xl p-6 mb-6">
                            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                                <input type="text" placeholder="🔍 Поиск..." class="input-modern" value="${filters.search}" onchange="filters.search=this.value; loadLots().then(() => renderCurrentView())">
                                <select class="input-modern" onchange="filters.category=this.value; loadLots().then(() => renderCurrentView())">
                                    <option value="">Все категории</option>
                                    ${categories.map(c => `<option value="${c}" ${filters.category===c?'selected':''}>${c}</option>`).join('')}
                                </select>
                                <input type="number" placeholder="ROI от %" class="input-modern" value="${filters.minRoi}" onchange="filters.minRoi=this.value; loadLots().then(() => renderCurrentView())">
                                <input type="number" placeholder="ROI до %" class="input-modern" value="${filters.maxRoi}" onchange="filters.maxRoi=this.value; loadLots().then(() => renderCurrentView())">
                            </div>
                            <button onclick="filters={search:'',category:'',minRoi:'',maxRoi:'',minBudget:'',maxBudget:''}; loadLots().then(() => renderCurrentView())" class="btn-primary">Сбросить фильтры</button>
                        </div>
                        
                        <div class="glass-strong rounded-xl p-6">
                            <h2 class="text-2xl font-bold text-white mb-6">📦 Лоты (${lots.length})</h2>
                            <div class="grid grid-cols-1 gap-4">
                                ${lots.map(lot => `
                                    <div class="glass rounded-xl p-6 card-hover ${lot.is_favorite ? 'border-2 border-yellow-400' : ''}">
                                        <div class="flex justify-between items-start mb-4">
                                            <div class="flex-1">
                                                <div class="flex items-center gap-2 mb-2">
                                                    ${lot.is_favorite ? '⭐' : ''}
                                                    ${lot.has_note ? '💬' : ''}
                                                    ${lot.is_won ? '✅' : ''}
                                                    ${lot.is_viewed ? '👁️' : ''}
                                                </div>
                                                <h3 class="text-xl font-bold text-white mb-2">${lot.simplified_name || lot.original_name}</h3>
                                                <p class="text-gray-400 text-sm">Лот: ${lot.lot_number}</p>
                                            </div>
                                            <div class="text-right">
                                                <div class="text-2xl font-bold text-purple-400">${lot.tender_price?.toLocaleString() || 0} ₸</div>
                                                <div class="text-gray-400 text-sm">${lot.quantity || 0} ${lot.unit || ''}</div>
                                            </div>
                                        </div>
                                        <div class="flex items-center justify-between pt-4 border-t border-gray-700">
                                            <div>
                                                ${lot.category ? `<span class="text-sm px-3 py-1 rounded-full bg-purple-500/20 text-purple-300">${lot.category}</span>` : ''}
                                                <span class="text-green-400 ml-2">💰 ${lot.stats.profit.toLocaleString()} ₸</span>
                                                <span class="text-yellow-400 ml-2">📊 ROI: ${lot.stats.roi.toFixed(1)}%</span>
                                            </div>
                                            <div class="flex gap-2">
                                                <button onclick="toggleFavorite('${lot.lot_number}')" class="btn-primary text-sm">${lot.is_favorite ? '⭐' : '☆'}</button>
                                                <button onclick="showLotDetail('${lot.lot_number}')" class="btn-primary text-sm">Детали</button>
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                `;
            } else if (currentView === 'favorites') {
                const favs = await loadFavorites();
                content = `
                    <div class="max-w-7xl mx-auto p-6">
                        <div class="glass-strong rounded-xl p-6">
                            <h2 class="text-2xl font-bold text-white mb-6">⭐ Избранное (${favs.length})</h2>
                            ${favs.length > 0 ? `
                                <div class="grid grid-cols-1 gap-4">
                                    ${favs.map(lot => `
                                        <div class="glass rounded-xl p-6 border-2 border-yellow-400">
                                            <h3 class="text-xl font-bold text-white mb-2">${lot.simplified_name || lot.original_name}</h3>
                                            <p class="text-gray-400">Прибыль: ${lot.stats.profit.toLocaleString()} ₸ | ROI: ${lot.stats.roi.toFixed(1)}%</p>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<p class="text-gray-400 text-center py-8">Нет избранных лотов</p>'}
                        </div>
                    </div>
                `;
            } else if (currentView === 'stats') {
                const stats = await loadStats();
                content = `
                    <div class="max-w-7xl mx-auto p-6">
                        <div class="glass-strong rounded-xl p-6">
                            <h2 class="text-2xl font-bold text-white mb-6">📈 Статистика</h2>
                            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <div class="glass rounded-xl p-4 text-center">
                                    <div class="text-3xl font-bold text-blue-400">${stats.viewed}</div>
                                    <div class="text-gray-300 text-sm mt-1">Просмотрено</div>
                                </div>
                                <div class="glass rounded-xl p-4 text-center">
                                    <div class="text-3xl font-bold text-yellow-400">${stats.favorites}</div>
                                    <div class="text-gray-300 text-sm mt-1">Избранное</div>
                                </div>
                                <div class="glass rounded-xl p-4 text-center">
                                    <div class="text-3xl font-bold text-purple-400">${stats.notes}</div>
                                    <div class="text-gray-300 text-sm mt-1">Заметок</div>
                                </div>
                                <div class="glass rounded-xl p-4 text-center">
                                    <div class="text-3xl font-bold text-green-400">${stats.won}</div>
                                    <div class="text-gray-300 text-sm mt-1">Выиграно</div>
                                </div>
                            </div>
                            <div class="mt-8 p-6 bg-purple-500/10 rounded-xl">
                                <h3 class="text-xl font-bold text-white mb-4">💰 Финансовая статистика</h3>
                                <p class="text-gray-300">Прогнозная прибыль: <span class="text-green-400 font-bold">${stats.total_profit.toLocaleString()} ₸</span></p>
                                <p class="text-gray-300">Средний ROI: <span class="text-yellow-400 font-bold">${stats.avg_roi.toFixed(1)}%</span></p>
                                <p class="text-gray-300">Win Rate: <span class="text-blue-400 font-bold">${stats.win_rate.toFixed(1)}%</span></p>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            document.getElementById('app').innerHTML = `
                <div class="min-h-screen">
                    ${header}
                    ${content}
                </div>
            `;
        }
        
        async function showLotDetail(lotNumber) {
            const res = await fetch(`/api/lots/${lotNumber}`);
            const lot = await res.json();
            
            const modal = document.createElement('div');
            modal.className = 'modal active';
            modal.innerHTML = `
                <div class="modal-content">
                    <div class="flex justify-between items-start mb-4">
                        <h2 class="text-2xl font-bold text-white">📦 ${lot.simplified_name || lot.original_name}</h2>
                        <button onclick="this.closest('.modal').remove()" class="text-white text-2xl">&times;</button>
                    </div>
                    <div class="text-gray-300 space-y-2">
                        <p><strong>Номер:</strong> ${lot.lot_number}</p>
                        <p><strong>Категория:</strong> ${lot.category || 'Не указана'}</p>
                        <p><strong>Цена тендера:</strong> ${lot.tender_price?.toLocaleString()} ₸</p>
                        <p><strong>Количество:</strong> ${lot.quantity} ${lot.unit || ''}</p>
                        <p><strong>Прибыль:</strong> <span class="text-green-400">${lot.stats.profit.toLocaleString()} ₸</span></p>
                        <p><strong>ROI:</strong> <span class="text-yellow-400">${lot.stats.roi.toFixed(1)}%</span></p>
                        <p><strong>Маржа:</strong> ${lot.stats.profit_margin.toFixed(1)}%</p>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        checkAuth();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
