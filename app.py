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
