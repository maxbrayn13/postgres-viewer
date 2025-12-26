# 📊 PostgreSQL Viewer для TenderFinder

Минималистичный веб-интерфейс для просмотра данных из Railway PostgreSQL.

## 🎯 Что показывает:

- ✅ Все лоты из таблицы `lots`
- ✅ Все товары из таблицы `search_results`
- ✅ Статистика (количество лотов, товаров)
- ✅ Детали каждого лота
- ✅ Красивый интерфейс

## 🚀 Деплой на Railway:

### 1. Создай новый проект на GitHub

```bash
git init
git add .
git commit -m "Initial commit: PostgreSQL Viewer"
git remote add origin https://github.com/YOUR_USERNAME/postgres-viewer.git
git push -u origin main
```

### 2. Создай новый сервис на Railway

1. Railway → New Project → Deploy from GitHub
2. Выбери репозиторий `postgres-viewer`
3. Deploy

### 3. Добавь переменную DATABASE_URL

1. Railway → postgres-viewer → Variables
2. New Variable → DATABASE_URL
3. Reference → Postgres → DATABASE_URL
4. Save

### 4. Готово!

Открой: `https://YOUR-APP.up.railway.app`

Увидишь все данные из PostgreSQL!

## 📊 Что увидишь:

### Статистика:
- Всего лотов: 53
- Всего товаров: 324
- Товаров на лот: ~6.1

### Лоты:
- Номер лота
- Название (упрощённое)
- Категория
- Цена
- Количество
- Сколько товаров найдено

### Товары:
- Таблица всех найденных товаров
- Ссылки на маркетплейсы
- Цены
- Названия

## 🔧 API Endpoints:

- `/` - Главная страница с данными
- `/api/data` - JSON со всеми данными
- `/health` - Проверка здоровья

## 📝 Структура проекта:

```
postgres-viewer/
├── app.py              # Главный файл Flask
├── requirements.txt    # Зависимости Python
├── Procfile           # Команда запуска
├── runtime.txt        # Версия Python
└── README.md          # Эта инструкция
```

## ✅ После деплоя:

Сайт покажет ВСЕ данные которые `tenderfinder_final.py` записал в PostgreSQL!
