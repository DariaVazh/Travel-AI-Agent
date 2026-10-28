import sqlite3
import json

# DB_PATH = "botD.db"
DB_PATH = "/app/data/botD.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Таблица для хранения истории диалогов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_histories (
                user_id INTEGER PRIMARY KEY,
                history TEXT
            )
        """)
        # Таблица для хранения данных регистрации (имя, телефон)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT
            )
        """)
        conn.commit()

def get_history(user_id: int) -> list:
    """Достает историю пользователя из БД"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT history FROM user_histories WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return []

def save_history(user_id: int, history: list):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        history_json = json.dumps(history, ensure_ascii=False)
        cursor.execute("""
            INSERT INTO user_histories (user_id, history) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET history = excluded.history
        """, (user_id, history_json))
        conn.commit()

def save_user(user_id: int, full_name: str, phone: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, full_name, phone) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                full_name = excluded.full_name, 
                phone = excluded.phone
        """, (user_id, full_name, phone))
        conn.commit()
def get_user(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "full_name": row[1],
                "phone": row[2]
            }
        return None