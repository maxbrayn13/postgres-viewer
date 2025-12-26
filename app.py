from flask import Flask, jsonify, request, session, render_template_string
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'tenderfinder-secret-2025')
CORS(app, supports_credentials=True)

DATABASE_URL = os.getenv('DATABASE_URL')

# Auth decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def calculate_stats(lot):
    """Расчёт статистики для лота"""
    best_price = lot['tender_price'] * 0.4 if lot.get('tender_price') else 0
    total_cost = best_price * (lot.get('quantity') or 0)
    delivery_cost = total_cost * 0.15
    total_expense = total_cost + delivery_cost
    revenue = (lot.get('tender_price') or 0) * (lot.get('quantity') or 0)
    profit = revenue - total_expense
    profit_margin = (profit / revenue * 100) if revenue > 0 else 0
    
    return {
        'best_price': round(best_price, 2),
        'total_cost': round(total_cost, 2),
        'delivery_cost': round(delivery_cost, 2),
        'total_expense': round(total_expense, 2),
        'revenue': round(revenue, 2),
        'profit': round(profit, 2),
        'profit_margin': round(profit_margin, 2)
    }

# ============= AUTHENTICATION =============

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Simple hardcoded auth
    if username == 'admin' and password == 'admin123':
        session['logged_in'] = True
        session['username'] = username
        session['is_admin'] = True
        return jsonify({
            "message": "Login successful",
            "user": {"username": username, "is_admin": True}
        })
    
    return jsonify({"error": "Invalid credentials"}), 401

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
                "username": session.get('username'),
                "is_admin": session.get('is_admin', False)
            }
        })
    return jsonify({"authenticated": False})

# ============= LOTS API =============

@app.route('/api/lots')
@login_required
def get_lots():
    try:
        search = request.args.get('search', '')
        category = request.args.get('category', '')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM lots WHERE 1=1"
        params = []
        
        if search:
            query += " AND (simplified_name ILIKE %s OR original_name ILIKE %s OR lot_number ILIKE %s)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        lots = cursor.fetchall()
        
        # Get product counts
        lots_with_counts = []
        for lot in lots:
            lot_dict = dict(lot)
            cursor.execute(
                "SELECT COUNT(*) as count FROM search_results WHERE lot_number = %s",
                [lot['lot_number']]
            )
            count_result = cursor.fetchone()
            lot_dict['product_count'] = count_result['count'] if count_result else 0
            lot_dict['stats'] = calculate_stats(lot)
            lots_with_counts.append(lot_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify({"lots": lots_with_counts})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/lots/<lot_number>')
@login_required
def get_lot_detail(lot_number):
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM lots WHERE lot_number = %s", [lot_number])
        lot = cursor.fetchone()
        
        if not lot:
            cursor.close()
            conn.close()
            return jsonify({"error": "Lot not found"}), 404
        
        cursor.execute(
            "SELECT * FROM search_results WHERE lot_number = %s ORDER BY created_at DESC",
            [lot_number]
        )
        products = cursor.fetchall()
        
        lot_dict = dict(lot)
        lot_dict['stats'] = calculate_stats(lot)
        lot_dict['products'] = [dict(p) for p in products]
        
        cursor.close()
        conn.close()
        
        return jsonify(lot_dict)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/categories')
@login_required  
def get_categories():
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT DISTINCT category FROM lots WHERE category IS NOT NULL AND category != ''")
        categories = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            "categories": [c['category'] for c in categories if c['category']]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
@login_required
def get_stats():
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT COUNT(*) as count FROM lots")
        total_lots = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) as count FROM search_results")
        total_products = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "total_lots": total_lots['count'] if total_lots else 0,
            "total_products": total_products['count'] if total_products else 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============= MAIN HTML =============

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
        
        .glass {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .glass-strong {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(30px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .card-hover {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .card-hover:hover {
            transform: translateY(-8px) scale(1.02);
            box-shadow: 0 20px 40px rgba(139, 92, 246, 0.3);
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            transition: all 0.3s ease;
            border: none;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
        }
        
        .btn-primary:hover {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(139, 92, 246, 0.4);
        }
        
        .input-modern {
            background: rgba(255, 255, 255, 0.05);
            border: 2px solid rgba(255, 255, 255, 0.1);
            color: white;
            padding: 12px;
            border-radius: 8px;
            transition: all 0.3s ease;
            width: 100%;
        }
        
        .input-modern:focus {
            background: rgba(255, 255, 255, 0.08);
            border-color: #8b5cf6;
            box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.1);
            outline: none;
        }
        
        .input-modern::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }
    </style>
</head>
<body class="animated-bg min-h-screen">
    <div id="app"></div>
    
    <script>
        let currentUser = null;
        let lots = [];
        let currentLot = null;
        
        async function checkAuth() {
            const res = await fetch('/api/check-auth');
            const data = await res.json();
            if (data.authenticated) {
                currentUser = data.user;
                showDashboard();
            } else {
                showLogin();
            }
        }
        
        function showLogin() {
            document.getElementById('app').innerHTML = `
                <div class="min-h-screen flex items-center justify-center p-4">
                    <div class="glass-strong rounded-2xl p-8 w-full max-w-md">
                        <h1 class="text-4xl font-bold text-white mb-2 text-center">🔍 TenderFinder Pro</h1>
                        <p class="text-gray-300 text-center mb-8">Умный поиск тендеров</p>
                        
                        <div id="loginError" class="hidden bg-red-500 text-white p-3 rounded-lg mb-4"></div>
                        
                        <input type="text" id="username" placeholder="Логин" class="input-modern mb-4">
                        <input type="password" id="password" placeholder="Пароль" class="input-modern mb-6">
                        <button onclick="login()" class="btn-primary w-full">Войти</button>
                        
                        <p class="text-gray-400 text-sm text-center mt-6">
                            По умолчанию: admin / admin123
                        </p>
                    </div>
                </div>
            `;
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
                showDashboard();
            } else {
                document.getElementById('loginError').textContent = data.error;
                document.getElementById('loginError').classList.remove('hidden');
            }
        }
        
        async function logout() {
            await fetch('/api/logout', {method: 'POST'});
            currentUser = null;
            showLogin();
        }
        
        async function showDashboard() {
            const statsRes = await fetch('/api/stats');
            const stats = await statsRes.json();
            
            const lotsRes = await fetch('/api/lots');
            const lotsData = await lotsRes.json();
            lots = lotsData.lots || [];
            
            document.getElementById('app').innerHTML = `
                <div class="min-h-screen p-6">
                    <div class="max-w-7xl mx-auto">
                        <div class="glass-strong rounded-2xl p-6 mb-6">
                            <div class="flex justify-between items-center">
                                <div>
                                    <h1 class="text-3xl font-bold text-white">🔍 TenderFinder Pro</h1>
                                    <p class="text-gray-300">Добро пожаловать, ${currentUser.username}!</p>
                                </div>
                                <button onclick="logout()" class="btn-primary">Выход</button>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-5xl font-bold text-purple-400">${stats.total_lots}</div>
                                <div class="text-gray-300 mt-2">Всего лотов</div>
                            </div>
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-5xl font-bold text-blue-400">${stats.total_products}</div>
                                <div class="text-gray-300 mt-2">Найдено товаров</div>
                            </div>
                            <div class="glass rounded-xl p-6 text-center">
                                <div class="text-5xl font-bold text-green-400">${(stats.total_products / stats.total_lots).toFixed(1)}</div>
                                <div class="text-gray-300 mt-2">Товаров на лот</div>
                            </div>
                        </div>
                        
                        <div class="glass-strong rounded-2xl p-6 mb-6">
                            <input type="text" id="searchInput" placeholder="🔍 Поиск по названию или номеру лота..." 
                                   class="input-modern" onkeyup="handleSearch()">
                        </div>
                        
                        <div class="glass-strong rounded-2xl p-6">
                            <h2 class="text-2xl font-bold text-white mb-6">📦 Лоты (${lots.length})</h2>
                            <div id="lotsList" class="grid grid-cols-1 gap-4"></div>
                        </div>
                    </div>
                </div>
            `;
            
            renderLots(lots);
        }
        
        function renderLots(lotsToRender) {
            const container = document.getElementById('lotsList');
            if (!lotsToRender || lotsToRender.length === 0) {
                container.innerHTML = '<p class="text-gray-400 text-center py-8">Лоты не найдены</p>';
                return;
            }
            
            container.innerHTML = lotsToRender.map(lot => `
                <div class="glass rounded-xl p-6 card-hover cursor-pointer" onclick="showLotDetail('${lot.lot_number}')">
                    <div class="flex justify-between items-start mb-4">
                        <div class="flex-1">
                            <h3 class="text-xl font-bold text-white mb-2">
                                ${lot.simplified_name || lot.original_name || 'Без названия'}
                            </h3>
                            <p class="text-gray-400 text-sm">Лот: ${lot.lot_number}</p>
                        </div>
                        <div class="text-right">
                            <div class="text-2xl font-bold text-purple-400">${(lot.tender_price || 0).toLocaleString()} ₸</div>
                            <div class="text-gray-400 text-sm">${lot.quantity || 0} ${lot.unit || ''}</div>
                        </div>
                    </div>
                    
                    <div class="flex items-center justify-between pt-4 border-t border-gray-700">
                        <div class="flex items-center gap-4">
                            ${lot.category ? `<span class="text-sm px-3 py-1 rounded-full bg-purple-500/20 text-purple-300">${lot.category}</span>` : ''}
                            <span class="text-sm text-gray-400">🛒 ${lot.product_count || 0} товаров</span>
                        </div>
                        <div class="text-sm">
                            <span class="text-green-400">💰 ${(lot.stats?.profit || 0).toLocaleString()} ₸</span>
                            <span class="text-gray-400 ml-2">(${(lot.stats?.profit_margin || 0).toFixed(1)}%)</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        async function showLotDetail(lotNumber) {
            const res = await fetch(`/api/lots/${lotNumber}`);
            const lot = await res.json();
            
            document.getElementById('app').innerHTML = `
                <div class="min-h-screen p-6">
                    <div class="max-w-7xl mx-auto">
                        <button onclick="showDashboard()" class="btn-primary mb-6">← Назад к списку</button>
                        
                        <div class="glass-strong rounded-2xl p-8 mb-6">
                            <h1 class="text-3xl font-bold text-white mb-4">
                                ${lot.simplified_name || lot.original_name}
                            </h1>
                            
                            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Номер лота</div>
                                    <div class="text-white font-semibold">${lot.lot_number}</div>
                                </div>
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Категория</div>
                                    <div class="text-white font-semibold">${lot.category || 'Не указана'}</div>
                                </div>
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Заказчик</div>
                                    <div class="text-white font-semibold">${lot.customer || 'Не указан'}</div>
                                </div>
                            </div>
                            
                            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 bg-purple-500/10 rounded-xl">
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Цена за единицу</div>
                                    <div class="text-2xl font-bold text-purple-400">${(lot.tender_price || 0).toLocaleString()} ₸</div>
                                </div>
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Количество</div>
                                    <div class="text-2xl font-bold text-blue-400">${lot.quantity || 0} ${lot.unit || ''}</div>
                                </div>
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Прибыль</div>
                                    <div class="text-2xl font-bold text-green-400">${(lot.stats?.profit || 0).toLocaleString()} ₸</div>
                                </div>
                                <div>
                                    <div class="text-gray-400 text-sm mb-1">Маржа</div>
                                    <div class="text-2xl font-bold text-yellow-400">${(lot.stats?.profit_margin || 0).toFixed(1)}%</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="glass-strong rounded-2xl p-8">
                            <h2 class="text-2xl font-bold text-white mb-6">🛍️ Найденные товары (${(lot.products || []).length})</h2>
                            
                            ${(lot.products && lot.products.length > 0) ? `
                                <div class="space-y-3">
                                    ${lot.products.map(p => `
                                        <div class="glass rounded-lg p-4 flex justify-between items-center">
                                            <div class="flex-1">
                                                <div class="text-white font-semibold mb-1">${p.product_title}</div>
                                                <div class="text-gray-400 text-sm">
                                                    ${p.marketplace} • ${p.product_price || 'Цена не указана'}
                                                </div>
                                            </div>
                                            <a href="${p.product_url}" target="_blank" class="btn-primary">Открыть →</a>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<p class="text-gray-400 text-center py-8">Товары не найдены</p>'}
                        </div>
                    </div>
                </div>
            `;
        }
        
        async function handleSearch() {
            const search = document.getElementById('searchInput').value;
            const res = await fetch(`/api/lots?search=${encodeURIComponent(search)}`);
            const data = await res.json();
            lots = data.lots || [];
            renderLots(lots);
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
