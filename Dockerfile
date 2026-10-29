# Этап 1: установка зависимостей
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Этап 2: финальное приложение
FROM python:3.12-slim-bookworm

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/
COPY agent/ ./agent/
COPY botD/ ./botD/
COPY database/ ./database/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080"]