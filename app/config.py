"""Секреты: из переменных окружения или из файла .env (строки вида NAME=value).
Файл .env ищется рядом с этим модулем, на уровень выше (корень репозитория) и в текущей папке запуска.
В Docker удобнее передавать переменные окружения (env_file в docker-compose): они читаются первыми."""
import os
from pathlib import Path


def _env_files():
    here = Path(__file__).resolve().parent
    seen = []
    for p in (here / ".env", here.parent / ".env", Path.cwd() / ".env"):
        if p not in seen:
            seen.append(p)
    return seen


def get_secret(name):
    v = os.getenv(name)
    if v:
        return v.strip().strip("\"'")
    for env in _env_files():
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == name and val.strip():
                return val.strip().strip("\"'")
    return None

