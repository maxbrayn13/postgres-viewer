# 🔍 TenderFinder Pro

Полноценная система управления тендерами с современным интерфейсом и мощным функционалом.

## ✨ Возможности:

### 🔐 Авторизация
- Защищённый вход в систему
- Session-based аутентификация
- Логин: `admin` / Пароль: `admin123`

### 📊 Статистика в реальном времени
- Общее количество лотов
- Количество найденных товаров
- Среднее количество товаров на лот

### 🔍 Поиск
- Мгновенный поиск по названию
- Поиск по номеру лота
- Фильтрация в реальном времени

### 📦 Управление лотами
- Красивые карточки лотов
- Детальная информация по каждому лоту
- Автоматический расчёт прибыли и маржи

### 🛍️ Товары
- Просмотр найденных товаров для каждого лота
- Прямые ссылки на маркетплейсы
- Информация о ценах и магазинах

### 🎨 Дизайн
- Анимированный фиолетовый градиент
- Glassmorphism эффекты
- Плавные анимации при наведении
- Адаптивная вёрстка
- TailwindCSS стилизация

## 🚀 Быстрый старт:

### Деплой на Railway:

1. **Создай GitHub репозиторий:**
```bash
git init
git add .
git commit -m "Initial commit: TenderFinder Pro"
git remote add origin https://github.com/YOUR_USERNAME/tenderfinder-pro.git
git push -u origin main
```

2. **Deploy на Railway:**
   - Railway → New Project → Deploy from GitHub
   - Выбери репозиторий `tenderfinder-pro`
   - Deploy

3. **Добавь переменную DATABASE_URL:**
   - Railway → tenderfinder-pro → Variables
   - New Variable → `DATABASE_URL`
   - Reference → Postgres → DATABASE_URL
   - Save

4. **Готово!**
   - Открой: `https://your-app.up.railway.app`
   - Войди: admin / admin123

## 📊 Архитектура:

```
tenderfinder-pro/
├── app.py              # Flask приложение (все в одном!)
│   ├── Backend API
│   ├── Авторизация
│   ├── База данных
│   └── Frontend (HTML/CSS/JS)
├── requirements.txt    # Python зависимости
├── Procfile           # Railway запуск
├── runtime.txt        # Python версия
└── README.md          # Документация
```

## 🔧 Технологии:

- **Backend:** Flask (Python)
- **Database:** PostgreSQL
- **Frontend:** JavaScript (Vanilla)
- **Styling:** TailwindCSS
- **Auth:** Flask Session
- **Deploy:** Railway

## 📋 API Endpoints:

### Авторизация
- `POST /api/login` - Вход в систему
- `POST /api/logout` - Выход
- `GET /api/check-auth` - Проверка авторизации

### Лоты
- `GET /api/lots` - Список лотов (с поиском)
- `GET /api/lots/<lot_number>` - Детали лота
- `GET /api/categories` - Категории
- `GET /api/stats` - Статистика

## 💡 Особенности:

### Расчёт прибыли:
```python
best_price = tender_price * 0.4  # 60% скидка
total_cost = best_price * quantity
delivery_cost = total_cost * 0.15  # 15% доставка
profit = revenue - (total_cost + delivery_cost)
profit_margin = (profit / revenue) * 100
```

### Session-based Auth:
- Безопасное хранение сессий
- Автоматический logout при закрытии
- Защита всех API endpoints

### SPA Interface:
- Без перезагрузки страницы
- Мгновенные переходы
- Плавные анимации

## 🎯 Использование:

1. **Вход:**
   - Логин: `admin`
   - Пароль: `admin123`

2. **Поиск:**
   - Введи название или номер лота
   - Результаты обновятся моментально

3. **Просмотр лота:**
   - Кликни на карточку лота
   - Увидишь детали и товары
   - Переходи по ссылкам на маркетплейсы

## 🔒 Безопасность:

- Session-based авторизация
- Защита всех API endpoints
- Secure cookies
- CORS настроен правильно

## 📱 Адаптивность:

- Работает на всех устройствах
- Mobile-friendly
- Responsive grid
- Touch-friendly интерфейс

## 🎨 Кастомизация:

### Изменить учётные данные:
```python
# В app.py, функция login()
if username == 'your_login' and password == 'your_password':
    # ...
```

### Изменить расчёт прибыли:
```python
# В app.py, функция calculate_stats()
best_price = lot['tender_price'] * 0.4  # Измени коэффициент
```

## 🐛 Troubleshooting:

### Пустая страница?
1. Проверь Railway Logs
2. Убедись что DATABASE_URL установлен
3. Проверь F12 Console на ошибки

### Не могу войти?
- Логин: `admin` (маленькими)
- Пароль: `admin123`

### Нет данных?
1. Проверь что PostgreSQL запущен
2. Убедись что tenderfinder_final.py записал данные
3. DATABASE_URL ссылается на правильную БД

## 📄 Лицензия:

MIT License - используй свободно!

## 🙏 Поддержка:

Если что-то не работает:
1. Проверь Railway Logs
2. Проверь DATABASE_URL
3. Проверь версию Python (3.11.7)

---

**Создано с ❤️ для эффективного управления тендерами!**
