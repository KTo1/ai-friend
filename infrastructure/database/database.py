import sqlite3
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name: str = "friend_bot.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_banned BOOLEAN DEFAULT FALSE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    age INTEGER,
                    interests TEXT,
                    mood TEXT,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # 🆕 ТАБЛИЦА ЛИМИТОВ ПОЛЬЗОВАТЕЛЕЙ
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_limits (
                    user_id INTEGER PRIMARY KEY,
                    max_daily_requests INTEGER DEFAULT 50,
                    max_message_length INTEGER DEFAULT 500,
                    max_context_messages INTEGER DEFAULT 5,
                    max_tokens_per_request INTEGER DEFAULT 1000,
                    custom_limits_enabled BOOLEAN DEFAULT FALSE,
                    messages_per_minute INTEGER DEFAULT 10,
                    messages_per_hour INTEGER DEFAULT 100,
                    minute_window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    minute_count INTEGER DEFAULT 0,
                    hour_window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hour_count INTEGER DEFAULT 0,                    
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # 🆕 ТАБЛИЦА СТАТИСТИКИ ИСПОЛЬЗОВАНИЯ
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_usage_stats (
                    user_id INTEGER,
                    date DATE DEFAULT CURRENT_DATE,
                    requests_count INTEGER DEFAULT 0,
                    total_tokens_used INTEGER DEFAULT 0,
                    total_cost_estimated REAL DEFAULT 0.0,
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # 🆕 ТАБЛИЦА АДМИНИСТРАТОРОВ
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    permissions_level INTEGER DEFAULT 1,  -- 1=moderator, 2=admin, 3=superadmin
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()

    def execute_query(self, query: str, params: tuple = ()):
        """Выполнить запрос к базе данных"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise

    def fetch_one(self, query: str, params: tuple = ()):
        """Получить одну запись"""
        cursor = self.execute_query(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params: tuple = ()):
        """Получить все записи"""
        cursor = self.execute_query(query, params)
        return cursor.fetchall()