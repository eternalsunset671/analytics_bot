# Telegram-бот AI-аналитики данных

Телеграм-бот, который анализирует CSV-данные с помощью LLM (Groq API). Пользователь загружает файл и получает AI-саммари, обнаружение аномалий, корреляционный анализ и тренды с графиками.

## Возможности

- `/summary` — описательная статистика + AI-интерпретация ключевых метрик
- `/anomalies` — обнаружение аномалий методом IQR + боксплоты и scatter-графики
- `/correlations` — корреляционный анализ + heatmap
- `/trends` — временные тренды, распределения категорий + графики
- `/demo` — демо-анализ на датасете Netflix Titles (8800+ записей)

Каждая команда возвращает аналитику (pandas + matplotlib) и текстовую AI-интерпретацию от LLM.

## Стек

- **Python 3.10+**
- **python-telegram-bot** — Telegram Bot API
- **Groq API** (Llama 3.3 70B) — LLM для интерпретации данных
- **pandas** — обработка данных
- **matplotlib** — визуализация
- **pydantic-settings** — управление конфигурацией

## Установка и запуск

### Требования

- Python 3.10+
- [Poetry](https://python-poetry.org/)
- Telegram Bot Token ([BotFather](https://t.me/BotFather))
- Groq API Key ([console.groq.com/keys](https://console.groq.com/keys))

### Локальный запуск

```bash
# Клонировать репозиторий
git clone https://github.com/eternalsunset671/analytics_bot.git
cd analytic_bot

# Установить зависимости
poetry install

# Создать .env файл
cp .env.example .env
# Заполнить TELEGRAM_BOT_TOKEN и GROQ_API_KEY в .env

# Запустить бота
poetry run python bot.py
```

### Docker

```bash
docker build -t analytic-bot .
docker run --env-file .env analytic-bot
```

## Использование

1. Найдите бота в Telegram
2. Отправьте `/start`
3. Загрузите CSV-файл (или используйте `/demo` для демо-датасета)
4. Вызовите нужную команду: `/summary`, `/anomalies`, `/correlations`, `/trends`

## Структура проекта

```
analytic_bot/
├── bot.py           # Главный файл бота, хэндлеры команд
├── analytics.py     # Аналитика: статистика, аномалии, корреляции, тренды
├── llm.py           # Взаимодействие с Groq LLM API
├── settings.py      # Pydantic-настройки из .env
├── demo.csv  # Демо-датасет
├── pyproject.toml   # Зависимости (Poetry)
├── Dockerfile       # Контейнеризация
└── README.md
```

## Деплой

Бот задеплоен и доступен в Telegram: **@boot_analytics_bot**.

