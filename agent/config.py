import os

import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "meta-llama/llama-3.3-70b-instruct:free",
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

HTTP_REFERER = os.getenv("HTTP_REFERER", "http://localhost:3000")
APP_TITLE = os.getenv("APP_TITLE", "Ostrovok Travel Agent")
