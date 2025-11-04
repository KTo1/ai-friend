import sqlite3
from typing import Optional
from datetime import datetime
from domain.entity.proactive_message import UserActivity
from infrastructure.database.database import Database


class ProactiveRepository:
    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы активности пользователей"""
        try:
            self.db.execute_query('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    user_id INTEGER PRIMARY KEY,
                    last_message_time TIMESTAMP,
                    last_proactive_time TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    timezone_offset INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Proactive repository table initialized")
        except Exception as e:
            print(f"Error initializing proactive table: {e}")

    def save_activity(self, activity: UserActivity):
        """Сохранить активность пользователя"""
        try:
            self.db.execute_query('''
                INSERT OR REPLACE INTO user_activity 
                (user_id, last_message_time, last_proactive_time, message_count, timezone_offset, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                activity.user_id,
                activity.last_message_time,
                activity.last_proactive_time,
                activity.message_count,
                activity.timezone_offset,
                datetime.now()
            ))
        except Exception as e:
            print(f"❌ Error saving activity: {e}")

    def get_activity(self, user_id: int) -> Optional[UserActivity]:
        """Получить активность пользователя"""
        try:
            result = self.db.fetch_one(
                'SELECT last_message_time, last_proactive_time, message_count, timezone_offset FROM user_activity WHERE user_id = ?',
                (user_id,)
            )

            if result:
                return UserActivity(
                    user_id=user_id,
                    last_message_time=datetime.fromisoformat(result[0]) if result[0] else datetime.now(),
                    last_proactive_time=datetime.fromisoformat(result[1]) if result[1] else None,
                    message_count=result[2] or 0,
                    timezone_offset=result[3] or 0
                )
            return None
        except Exception as e:
            print(f"❌ Error getting activity: {e}")
            return None