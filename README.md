# Telegram-бот AI-аналитики данных (агентная версия)

Телеграм-бот, в котором LLM выступает автономным аналитиком данных: пользователь присылает CSV/Excel с опциональной инструкцией, а LLM через tool-calling сама пишет и выполняет Python-код над датасетом, строит графики и возвращает отчёт с инсайдами.

## Как это работает (ключевое отличие)

LLM **не получает готовую статистику в промпт**. Вместо этого:

1. Бот передаёт LLM структуру датасета (размеры, имена и типы столбцов) и инструкцию пользователя.
2. LLM через механизм **function calling** вызывает инструмент `python_exec` с собственным Python-кодом.
3. Бот выполняет код в ограниченном окружении (`df`, `pd`, `np`, `plt` доступны; `os/sys/subprocess/open/сеть` — запрещены) и возвращает LLM `stdout`, `stderr`, исключения и сохранённые фигуры matplotlib.
4. LLM видит результат, при необходимости вызывает `python_exec` ещё раз — так до 8 итераций.
5. Когда LLM готова, она перестаёт вызывать инструмент и выдаёт финальный отчёт — бот отправляет его в чат вместе с графиками.

Это настоящая агентная петля: LLM сама принимает решения, какой код выполнить, и сама интерпретирует результаты.

## Возможности

- Анализ любого CSV/Excel-датасета «из коробки», без захардкоженных правил.
- Свободная инструкция пользователя — на что обратить внимание (передаётся либо в caption к файлу, либо через `/analyze <текст>`).
- Автоматически построенные графики (matplotlib) возвращаются в чат.
- Демо-режим на датасете Netflix Titles (8800+ записей).
- Защита от prompt-injection:
  - инструкция пользователя изолируется в тегах `<user_instruction>` и системным промптом трактуется как данные, а не команды;
  - регулярочные эвристики детектируют типичные атаки («ignore previous instructions», «забудь инструкции», «reveal system prompt», «DAN mode» и т.п.) — бот предупреждает пользователя и явно сообщает об этом LLM;
  - ограничение длины инструкции (1000 символов).
- Sandbox для кода LLM:
  - блоклист на `import os/sys/subprocess/socket/shutil/pathlib/requests/urllib/httpx`, `__import__`, `open()`, `eval/exec/compile`, `os.*`, `subprocess.*`, `sys.*`, `.read_csv/.to_csv` (чтение чужих файлов) и рефлексию (`__class__`, `__subclasses__`);
  - таймаут выполнения (25 секунд на один вызов) через отдельный поток;
  - лимит на размер вывода инструмента и на количество графиков.

## Команды

- `/analyze <инструкция>` — запустить агента со свободной инструкцией
- `/summary` — общий разведочный анализ
- `/anomalies` — фокус на выбросах и аномалиях
- `/correlations` — фокус на корреляциях и мультиколлинеарности
- `/trends` — фокус на временных трендах и распределениях
- `/demo` — переключиться на демо-датасет
- `/help` — справка

Главный сценарий: отправьте CSV/Excel, в подпись к файлу напишите, на что обратить внимание — агент запустится сразу.

## Стек

- **Python 3.10+**
- **python-telegram-bot** — Telegram Bot API
- **Groq API** (Llama 3.3 70B Versatile) — LLM с поддержкой function calling
- **pandas / numpy / matplotlib** — среда, доступная агенту внутри `python_exec`
- **pydantic-settings** — конфигурация

## Структура проекта

```
analytic_bot/
├── bot.py          # Telegram-хендлеры, маршрутизация команд, sanitize инструкций
├── agent.py        # Агентный цикл + python_exec sandbox + защита от prompt-injection
├── llm.py          # Тонкая обёртка над Groq Chat Completions (с tools)
├── analytics.py    # Только load_file (CSV/Excel)
├── settings.py     # Pydantic-настройки из .env
├── demo.csv        # Демо-датасет (Netflix Titles)
├── pyproject.toml  # Зависимости (Poetry)
├── Dockerfile      # Контейнеризация
└── README.md
```

## Установка и запуск

### Требования

- Python 3.10+
- [Poetry](https://python-poetry.org/)
- Telegram Bot Token ([BotFather](https://t.me/BotFather))
- Groq API Key ([console.groq.com/keys](https://console.groq.com/keys))

### Локальный запуск

```bash
git clone https://github.com/eternalsunset671/analytics_bot.git
cd analytic_bot

poetry install

cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и GROQ_API_KEY

poetry run python bot.py
```

### Docker

```bash
docker build -t analytic-bot .
docker run --env-file .env analytic-bot
```

## Использование

1. Найдите бота в Telegram.
2. Отправьте `/start`.
3. Загрузите CSV/Excel-файл. В подписи к файлу можно написать инструкцию: «сфокусируйся на продажах по регионам», «найди аномалии в колонке revenue», «посмотри сезонность».
4. Либо используйте `/demo`, а затем `/analyze <инструкция>` или один из пресетов (`/summary`, `/anomalies`, `/correlations`, `/trends`).
5. Дождитесь отчёта агента и графиков.

## Примеры использования

1. Запуск `/start`

![alt text](images/image.png)

2. Примеры с заготовленными промптами

![alt text](images/image-1.png)
![alt text](images/image-2.png)
![alt text](images/image-3.png)
![alt text](images/image-4.png)
![alt text](images/image-5.png)
![alt text](images/image-6.png)

3. Кастомная инструкция

![alt text](images/image-7.png)
![alt text](images/image-8.png)

4. Загрузка нового датасета

![alt text](images/image-9.png)
5. Неудачная промпт-инъекция

![alt text](images/image-10.png)

6. Кастомная инструкция к новому датасету

![alt text](images/image-11.png)