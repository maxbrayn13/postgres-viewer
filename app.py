from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_data():
    """Получить все данные из PostgreSQL"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем лоты
        cursor.execute("SELECT * FROM lots ORDER BY created_at DESC")
        lots = cursor.fetchall()
        
        # Получаем товары
        cursor.execute("SELECT * FROM search_results")
        products = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            'lots': [dict(lot) for lot in lots],
            'products': [dict(p) for p in products]
        }
    except Exception as e:
        return {'error': str(e), 'lots': [], 'products': []}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PostgreSQL Viewer - TenderFinder Data</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }
        .stat-number {
            font-size: 3rem;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }
        .stat-label {
            color: #666;
            font-size: 1.1rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .section {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8rem;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }
        td {
            padding: 15px;
            border-bottom: 1px solid #eee;
            color: #333;
        }
        tr:hover {
            background: #f8f9ff;
        }
        .lot-card {
            background: #f8f9ff;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
        }
        .lot-title {
            font-size: 1.2rem;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }
        .lot-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .lot-info-item {
            display: flex;
            flex-direction: column;
        }
        .lot-info-label {
            color: #666;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .lot-info-value {
            color: #333;
            font-size: 1.1rem;
            font-weight: 600;
        }
        .product-count {
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            display: inline-block;
            margin-top: 10px;
        }
        .error {
            background: #ff4444;
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 20px;
        }
        .refresh-btn {
            background: white;
            color: #667eea;
            border: none;
            padding: 15px 30px;
            border-radius: 25px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            margin: 20px auto;
            display: block;
            transition: all 0.3s;
        }
        .refresh-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.3);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 PostgreSQL Viewer - TenderFinder</h1>
        
        {% if data.error %}
        <div class="error">
            ❌ Ошибка подключения к БД: {{ data.error }}
        </div>
        {% endif %}
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ data.lots|length }}</div>
                <div class="stat-label">Всего лотов</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ data.products|length }}</div>
                <div class="stat-label">Всего товаров</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ (data.products|length / data.lots|length)|round(1) if data.lots|length > 0 else 0 }}</div>
                <div class="stat-label">Товаров на лот</div>
            </div>
        </div>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Обновить данные</button>
        
        <div class="section">
            <h2>📦 Лоты ({{ data.lots|length }})</h2>
            
            {% for lot in data.lots %}
            <div class="lot-card">
                <div class="lot-title">{{ lot.simplified_name or lot.original_name }}</div>
                
                <div class="lot-info">
                    <div class="lot-info-item">
                        <span class="lot-info-label">Номер лота</span>
                        <span class="lot-info-value">{{ lot.lot_number }}</span>
                    </div>
                    <div class="lot-info-item">
                        <span class="lot-info-label">Категория</span>
                        <span class="lot-info-value">{{ lot.category or 'Не указана' }}</span>
                    </div>
                    <div class="lot-info-item">
                        <span class="lot-info-label">Цена</span>
                        <span class="lot-info-value">{{ "{:,.2f}".format(lot.tender_price) if lot.tender_price else '—' }} ₸</span>
                    </div>
                    <div class="lot-info-item">
                        <span class="lot-info-label">Количество</span>
                        <span class="lot-info-value">{{ lot.quantity or '—' }} {{ lot.unit or '' }}</span>
                    </div>
                </div>
                
                {% set lot_products = data.products|selectattr('lot_number', 'equalto', lot.lot_number)|list %}
                <span class="product-count">🛒 {{ lot_products|length }} товаров найдено</span>
            </div>
            {% endfor %}
            
            {% if not data.lots %}
            <p style="text-align: center; color: #999; padding: 40px;">Нет данных</p>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>🛍️ Найденные товары ({{ data.products|length }})</h2>
            
            <table>
                <thead>
                    <tr>
                        <th>Лот</th>
                        <th>Товар</th>
                        <th>Цена</th>
                        <th>Маркетплейс</th>
                        <th>Ссылка</th>
                    </tr>
                </thead>
                <tbody>
                    {% for product in data.products[:100] %}
                    <tr>
                        <td>{{ product.lot_number }}</td>
                        <td>{{ product.product_title[:80] }}...</td>
                        <td>{{ product.product_price }}</td>
                        <td>{{ product.marketplace }}</td>
                        <td><a href="{{ product.product_url }}" target="_blank" style="color: #667eea;">🔗 Открыть</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            {% if data.products|length > 100 %}
            <p style="text-align: center; color: #999; margin-top: 20px;">
                Показано 100 из {{ data.products|length }} товаров
            </p>
            {% endif %}
            
            {% if not data.products %}
            <p style="text-align: center; color: #999; padding: 40px;">Нет данных</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    data = get_db_data()
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/api/data')
def api_data():
    return jsonify(get_db_data())

@app.route('/health')
def health():
    return jsonify({"status": "ok", "database": "connected" if DATABASE_URL else "not configured"})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
