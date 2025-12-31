#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TenderFinder Commercial - Используем SQLite для users (как в старом проекте)
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'tenderfinder-secret-key-2025')
CORS(app, supports_credentials=True)

# PostgreSQL для данных тендеров
DATABASE_URL = os.getenv('DATABASE_URL')

# SQLite для пользователей (как в старом проекте!)
USERS_DB = 'users.db'

# ============================================================================
# DATABASE - SQLite для пользователей
# ============================================================================

def init_users_db():
    """Инициализация SQLite базы для пользователей"""
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        has_access INTEGER DEFAULT 0,
        access_until TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Создать админа если нет
    c.execute('SELECT * FROM users WHERE email = ?', ('admin@tenderfinder.com',))
    if not c.fetchone():
        c.execute('''INSERT INTO users (email, password_hash, is_admin, has_access) 
                     VALUES (?, ?, ?, ?)''',
                  ('admin@tenderfinder.com', generate_password_hash('admin123'), 1, 1))
    
    conn.commit()
    conn.close()

# Инициализация при старте
init_users_db()

# ============================================================================
# DATABASE - PostgreSQL для тендеров
# ============================================================================

def get_db_connection():
    """Получить подключение к PostgreSQL"""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return None

# ============================================================================
# AUTH HELPERS
# ============================================================================

def get_current_user():
    """Получить текущего пользователя из сессии"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    
    return dict(user) if user else None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user['is_admin']:
            flash('Доступ запрещен. Требуются права администратора.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('login'))
        
        if not user['has_access']:
            flash('У вас нет доступа к каталогу. Обратитесь к администратору.', 'warning')
            return redirect(url_for('index'))
        
        # Проверка срока доступа
        if user['access_until']:
            access_until = datetime.fromisoformat(user['access_until'])
            if access_until < datetime.now():
                flash('Срок вашего доступа истек. Обратитесь к администратору.', 'warning')
                return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# ROUTES - PUBLIC
# ============================================================================

@app.route('/')
def index():
    """Главная страница"""
    user = get_current_user()
    return render_template('index.html', current_user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if not email or not password:
            flash('Заполните все поля', 'danger')
            return redirect(url_for('register'))
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))
        
        # Проверка существующего пользователя
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        if c.fetchone():
            conn.close()
            flash('Пользователь с таким email уже существует', 'danger')
            return redirect(url_for('register'))
        
        # Создание пользователя
        c.execute('''INSERT INTO users (email, password_hash, is_admin, has_access) 
                     VALUES (?, ?, ?, ?)''',
                  (email, generate_password_hash(password), 0, 0))
        conn.commit()
        conn.close()
        
        flash('Регистрация успешна! Дождитесь активации администратором.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в систему"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash(f'Добро пожаловать, {email}!', 'success')
            
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('catalog'))
        
        flash('Неверный email или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# ============================================================================
# ROUTES - CATALOG
# ============================================================================

@app.route('/catalog')
@access_required
def catalog():
    """Каталог тендеров с фильтрами"""
    if not DATABASE_URL:
        flash('База данных тендеров не настроена', 'danger')
        return redirect(url_for('index'))
    
    # Получение параметров фильтрации
    country_kz = request.args.get('country_kz', '1') == '1'
    country_ru = request.args.get('country_ru', '1') == '1'
    country_cn = request.args.get('country_cn', '1') == '1'
    
    deposit = request.args.get('deposit', type=float)
    margin = request.args.get('margin', type=float)
    
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Базовый запрос
        where_clauses = []
        params = []
        
        # Фильтр по поиску
        if search:
            where_clauses.append("(l.original_name ILIKE %s OR l.simplified_name ILIKE %s)")
            params.extend([f'%{search}%', f'%{search}%'])
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Подсчет общего количества
        cursor.execute(f"SELECT COUNT(*) as total FROM lots l WHERE {where_sql}", params)
        total_count = cursor.fetchone()['total']
        
        # Получение лотов с пагинацией
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT l.*, 
                   COUNT(DISTINCT sr.id) as products_count
            FROM lots l
            LEFT JOIN search_results sr ON l.lot_number = sr.lot_number
            WHERE {where_sql}
            GROUP BY l.id
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])
        
        lots = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Рассчет пагинации
        total_pages = (total_count + per_page - 1) // per_page
        
        return render_template('catalog.html',
            lots=lots,
            total_count=total_count,
            page=page,
            total_pages=total_pages,
            country_kz=country_kz,
            country_ru=country_ru,
            country_cn=country_cn,
            deposit=deposit,
            margin=margin,
            search=search,
            current_user=get_current_user()
        )
    except Exception as e:
        flash(f'Ошибка загрузки каталога: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/lot/<lot_number>')
@access_required
def lot_detail(lot_number):
    """Детальная информация о лоте"""
    if not DATABASE_URL:
        flash('База данных тендеров не настроена', 'danger')
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получение информации о лоте
        cursor.execute("SELECT * FROM lots WHERE lot_number = %s", [lot_number])
        lot = cursor.fetchone()
        
        if not lot:
            cursor.close()
            conn.close()
            flash('Лот не найден', 'danger')
            return redirect(url_for('catalog'))
        
        # Получение товаров
        cursor.execute("""
            SELECT * FROM search_results 
            WHERE lot_number = %s 
            ORDER BY marketplace, product_price
        """, [lot_number])
        products = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Группировка товаров по странам
        products_by_country = {
            'KZ': [],
            'RU': [],
            'CN': []
        }
        
        for product in products:
            marketplace = product.get('marketplace', '').lower()
            if any(x in marketplace for x in ['aliexpress', 'pinduoduo', 'taobao', '1688']):
                products_by_country['CN'].append(product)
            elif 'kaspi' in marketplace or 'satu' in marketplace or 'ozon.kz' in marketplace:
                products_by_country['KZ'].append(product)
            else:
                products_by_country['RU'].append(product)
        
        return render_template('lot_detail.html',
            lot=lot,
            products_by_country=products_by_country,
            total_products=len(products),
            current_user=get_current_user()
        )
    except Exception as e:
        flash(f'Ошибка загрузки лота: {str(e)}', 'danger')
        return redirect(url_for('catalog'))

# ============================================================================
# ROUTES - ADMIN
# ============================================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Панель администратора"""
    # Статистика пользователей
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM users WHERE is_admin = 0")
    users_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) as total FROM users WHERE has_access = 1 AND is_admin = 0")
    active_users = c.fetchone()[0]
    conn.close()
    
    # Статистика тендеров
    lots_count = 0
    products_count = 0
    
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM lots")
            lots_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM search_results")
            products_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
        except:
            pass
    
    return render_template('admin/dashboard.html',
        users_count=users_count,
        active_users=active_users,
        lots_count=lots_count,
        products_count=products_count,
        current_user=get_current_user()
    )

@app.route('/admin/users')
@admin_required
def admin_users():
    """Управление пользователями"""
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, email, has_access, access_until, created_at
        FROM users 
        WHERE is_admin = 0
        ORDER BY created_at DESC
    """)
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return render_template('admin/users.html', 
        users=users, 
        now=datetime.now(),
        current_user=get_current_user()
    )

@app.route('/admin/users/<int:user_id>/toggle-access', methods=['POST'])
@admin_required
def admin_toggle_access(user_id):
    """Включить/выключить доступ пользователя"""
    days = request.form.get('days', type=int)
    
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    
    if days and days > 0:
        # Открыть доступ на N дней
        access_until = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute("UPDATE users SET has_access = 1, access_until = ? WHERE id = ?",
                  (access_until, user_id))
        flash(f'Доступ открыт на {days} дней', 'success')
    else:
        # Закрыть доступ
        c.execute("UPDATE users SET has_access = 0, access_until = NULL WHERE id = ?",
                  (user_id,))
        flash('Доступ закрыт', 'success')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_users'))

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/stats')
def api_stats():
    """API для получения статистики"""
    lots_count = 0
    products_count = 0
    by_marketplace = {}
    
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT COUNT(*) as total FROM lots")
            lots_count = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as total FROM search_results")
            products_count = cursor.fetchone()['total']
            
            cursor.execute("""
                SELECT marketplace, COUNT(*) as count 
                FROM search_results 
                GROUP BY marketplace
            """)
            by_marketplace = {row['marketplace']: row['count'] for row in cursor.fetchall()}
            
            cursor.close()
            conn.close()
        except:
            pass
    
    return jsonify({
        'lots': lots_count,
        'products': products_count,
        'by_marketplace': by_marketplace
    })

# ============================================================================
# TEMPLATE CONTEXT
# ============================================================================

@app.context_processor
def inject_user():
    """Добавить current_user во все шаблоны"""
    return dict(current_user=get_current_user())

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
