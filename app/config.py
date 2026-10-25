"""Секреты: из переменных окружения или из файла .env рядом с проектом (строки вида NAME=value)."""
import os
from pathlib import Path


def get_secret(name):
    v = os.getenv(name)
    if v:
        return v.strip().strip("\"'")
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == name:
                return val.strip().strip("\"'")
    return None
