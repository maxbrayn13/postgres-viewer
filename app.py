#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TenderFinder Commercial - Профессиональная платформа для поиска тендеров
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'tenderfinder-secret-key-2025')

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:SurRXlBLOwOtKJlWSYAGNNylwQLVoyEZ@gondola.proxy.rlwy.net:39585/railway')

# Login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def get_db_connection():
    """Получить подключение к базе данных"""
    return psycopg2.connect(DATABASE_URL)

# ============================================================================
# USER MODEL
# ============================================================================

class User:
    def __init__(self, id, email, password_hash, is_admin=False, has_access=False, access_until=None):
        self.id = id
        self.email = email
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.has_access = has_access
        self.access_until = access_until
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return str(self.id)
    
    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user_data:
            return User(**user_data)
        return None
    
    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email = %s", [email])
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user_data:
            return User(**user_data)
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# ============================================================================
# DECORATORS
# ============================================================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Доступ запрещен. Требуются права администратора.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('login'))
        
        if not current_user.has_access:
            flash('У вас нет доступа к каталогу. Обратитесь к администратору.', 'warning')
            return redirect(url_for('index'))
        
        if current_user.access_until and current_user.access_until < datetime.now():
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
    return render_template('index.html')

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
        if User.get_by_email(email):
            flash('Пользователь с таким email уже существует', 'danger')
            return redirect(url_for('register'))
        
        # Создание пользователя
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (email, password_hash, is_admin, has_access)
            VALUES (%s, %s, %s, %s)
        """, [email, generate_password_hash(password), False, False])
        conn.commit()
        cursor.close()
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
        
        user = User.get_by_email(email)
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f'Добро пожаловать, {email}!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('catalog'))
        
        flash('Неверный email или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# ============================================================================
# ROUTES - CATALOG
# ============================================================================

@app.route('/catalog')
@access_required
def catalog():
    """Каталог тендеров с фильтрами"""
    # Получение параметров фильтрации
    country_kz = request.args.get('country_kz', '1') == '1'
    country_ru = request.args.get('country_ru', '1') == '1'
    country_cn = request.args.get('country_cn', '1') == '1'
    
    deposit = request.args.get('deposit', type=float)
    margin = request.args.get('margin', type=float)
    
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Построение SQL запроса
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Базовый запрос
    where_clauses = []
    params = []
    
    # Фильтр по странам (через marketplace в search_results)
    countries = []
    if country_kz:
        countries.append('KZ')
    if country_ru:
        countries.append('RU')
    if country_cn:
        countries.extend(['aliexpress', 'pinduoduo', 'taobao', '1688'])
    
    if countries:
        country_placeholders = ','.join(['%s'] * len(countries))
        where_clauses.append(f"EXISTS (SELECT 1 FROM search_results sr WHERE sr.lot_number = l.lot_number AND sr.marketplace IN ({country_placeholders}))")
        params.extend(countries)
    
    # Фильтр по поиску
    if search:
        where_clauses.append("(l.original_name ILIKE %s OR l.simplified_name ILIKE %s)")
        params.extend([f'%{search}%', f'%{search}%'])
    
    # Фильтр по депозиту (сумма товаров <= депозит)
    if deposit:
        where_clauses.append("""
            EXISTS (
                SELECT 1 FROM search_results sr 
                WHERE sr.lot_number = l.lot_number 
                GROUP BY sr.lot_number
                HAVING SUM(CAST(REPLACE(REPLACE(sr.product_price, '¥', ''), ',', '') AS DECIMAL) * l.quantity) <= %s
            )
        """)
        params.append(deposit)
    
    # Фильтр по марже (цена тендера - сумма товаров >= желаемая маржа)
    if margin:
        where_clauses.append("""
            EXISTS (
                SELECT 1 FROM search_results sr 
                WHERE sr.lot_number = l.lot_number 
                GROUP BY sr.lot_number
                HAVING (l.tender_price - SUM(CAST(REPLACE(REPLACE(sr.product_price, '¥', ''), ',', '') AS DECIMAL) * l.quantity)) >= %s
            )
        """)
        params.append(margin)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Подсчет общего количества
    cursor.execute(f"""
        SELECT COUNT(DISTINCT l.lot_number) as total
        FROM lots l
        WHERE {where_sql}
    """, params)
    total_count = cursor.fetchone()['total']
    
    # Получение лотов с пагинацией
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT DISTINCT ON (l.lot_number)
            l.*, 
            COUNT(sr.id) OVER (PARTITION BY l.lot_number) as products_count,
            MIN(CAST(REPLACE(REPLACE(sr.product_price, '¥', ''), ',', '') AS DECIMAL)) OVER (PARTITION BY l.lot_number) as min_price
        FROM lots l
        LEFT JOIN search_results sr ON l.lot_number = sr.lot_number
        WHERE {where_sql}
        ORDER BY l.lot_number, l.created_at DESC
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
        search=search
    )

@app.route('/lot/<lot_number>')
@access_required
def lot_detail(lot_number):
    """Детальная информация о лоте"""
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
        if product['marketplace'] in ['aliexpress', 'pinduoduo', 'taobao', '1688']:
            products_by_country['CN'].append(product)
        elif product['marketplace'] == 'RU':
            products_by_country['RU'].append(product)
        else:
            products_by_country['KZ'].append(product)
    
    return render_template('lot_detail.html',
        lot=lot,
        products_by_country=products_by_country,
        total_products=len(products)
    )

# ============================================================================
# ROUTES - ADMIN
# ============================================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Панель администратора"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Статистика
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE NOT is_admin")
    users_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE has_access AND NOT is_admin")
    active_users = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM lots")
    lots_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM search_results")
    products_count = cursor.fetchone()['total']
    
    cursor.close()
    conn.close()
    
    return render_template('admin/dashboard.html',
        users_count=users_count,
        active_users=active_users,
        lots_count=lots_count,
        products_count=products_count
    )

@app.route('/admin/users')
@admin_required
def admin_users():
    """Управление пользователями"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT id, email, has_access, access_until, created_at
        FROM users 
        WHERE NOT is_admin
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/<int:user_id>/toggle-access', methods=['POST'])
@admin_required
def admin_toggle_access(user_id):
    """Включить/выключить доступ пользователя"""
    days = request.form.get('days', type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if days and days > 0:
        # Открыть доступ на N дней
        access_until = datetime.now() + timedelta(days=days)
        cursor.execute("""
            UPDATE users 
            SET has_access = TRUE, access_until = %s 
            WHERE id = %s
        """, [access_until, user_id])
        flash(f'Доступ открыт на {days} дней', 'success')
    else:
        # Закрыть доступ
        cursor.execute("""
            UPDATE users 
            SET has_access = FALSE, access_until = NULL 
            WHERE id = %s
        """, [user_id])
        flash('Доступ закрыт', 'success')
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('admin_users'))

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/stats')
@login_required
def api_stats():
    """API для получения статистики"""
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
    by_marketplace = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'lots': lots_count,
        'products': products_count,
        'by_marketplace': {row['marketplace']: row['count'] for row in by_marketplace}
    })

# ============================================================================
# INITIALIZATION
# ============================================================================

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Создание таблицы пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            has_access BOOLEAN DEFAULT FALSE,
            access_until TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Создание admin пользователя
    admin_email = 'admin@tenderfinder.com'
    cursor.execute("SELECT id FROM users WHERE email = %s", [admin_email])
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (email, password_hash, is_admin, has_access)
            VALUES (%s, %s, %s, %s)
        """, [admin_email, generate_password_hash('admin123'), True, True])
    
    conn.commit()
    cursor.close()
    conn.close()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
