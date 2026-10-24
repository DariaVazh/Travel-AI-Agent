# Free Penguins — Ostrovok Hackathon 2026

Проект команды Free Penguins для Ostrovok Hackathon 2026.

## Требования

- Docker Desktop с запущенным Docker Engine
- Docker Compose
- Git для клонирования репозитория

Локальная установка Python и библиотек не требуется.

## Запуск

1. Клонировать репозиторий:

   ```bash
   git clone https://github.com/ostrovok-hackathon-2026/free-penguins.git
   cd free-penguins
   ```

2. Создать файл `.env` на основе шаблона:

   Для PowerShell:
   ```powershell
   Copy-Item .env.example .env
   ```

   Для Linux/macOS:
   ```bash
   cp .env.example .env
   ```

3. Собрать и запустить приложение:

   ```bash
   docker compose up --build
   ```

4. Проверить работоспособность:

   - Приложение: http://localhost:8080/
   - Healthcheck: http://localhost:8080/health
   - Ожидаемый ответ: `{"status":"ok"}`

## Проверка контейнеров

```bash
docker compose ps
```

Статус сервиса `app` должен быть `healthy`.

## Остановка

```bash
docker compose down
```

## Переменные окружения

Переменные задаются в локальном `.env`. Файл `.env.example` содержит шаблон и включён в репозиторий.

Не добавляйте реальные API-ключи и токены в Git.

## Текущее состояние

Docker-инфраструктура запускает тестовое FastAPI-приложение. Интеграция AI-агента и интерфейса находится в разработке.

