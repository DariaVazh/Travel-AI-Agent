# Free Penguins — AI Travel Assistant 🐧

Интеллектуальный помощник для планирования путешествий на базе ИИ-агента.

Пользователь взаимодействует с Telegram-ботом, который помогает подобрать поездку с учётом направления, бюджета и предпочтений.

## Архитектура проекта

Приложение состоит из двух Docker-сервисов:

| Сервис | Назначение |
|---|---|
| `app` | FastAPI-приложение, API для планирования поездок |
| `bot` | Telegram-бот на aiogram с интеграцией ИИ-агента |

Дополнительно используется SQLite для хранения истории диалогов и регистрационных данных пользователей. Данные сохраняются в Docker volume `bot_data`.

Основные компоненты проекта:

- `app/` — backend, поиск и обработка туристических предложений.
- `agent/` — логика ИИ-агента.
- `bot/` — Telegram-бот и работа с пользовательскими данными.

## Требования

Для запуска необходимы:

- Docker Desktop или Docker Engine с Docker Compose
- Git
- Доступ к интернету
- Необходимые API-ключи, включая токен Telegram-бота

Устанавливать Python и библиотеки вручную не требуется.

## Быстрый запуск

**1. Клонировать репозиторий**

```bash
git clone <REPOSITORY_URL>
cd free-penguins
```

**2. Настроить переменные окружения**

Скопировать `.env.example` в `.env`:

```bash
cp .env.example .env
```

Для Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Заполнить необходимые переменные окружения.

**3. Запустить приложение**

```bash
docker compose up --build
```

Docker автоматически соберёт необходимые образы и запустит сервисы.

**4. Проверить работу**

FastAPI доступен по адресу:

http://localhost:8080

Проверка работоспособности:

http://localhost:8080/health

Telegram-бот:

https://t.me/travel_O_island_bot

После запуска можно открыть Telegram-бота, отправить `/start` и воспользоваться меню «Найти поездку».

## Управление контейнерами

Запуск в фоновом режиме:

```bash
docker compose up -d --build
```

Просмотр состояния:

```bash
docker compose ps
```

Логи Telegram-бота:

```bash
docker compose logs -f botD
```

Логи backend:

```bash
docker compose logs -f app
```

Остановка приложения:

```bash
docker compose down
```

## Хранение данных

Для хранения пользовательских данных используется SQLite.

База находится по пути `/app/data/bot.db` внутри контейнера `bot`.

Docker volume `bot_data` обеспечивает сохранение данных при пересоздании контейнеров.

Команда `docker compose down` не удаляет сохранённые данные.

## Технологии

- Python
- FastAPI
- aiogram
- ИИ-агент на базе LLM
- SQLite
- Docker / Docker Compose

## Команда

Free Penguins — Ostrovok Hackathon 2026.
