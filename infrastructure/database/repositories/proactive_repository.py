import json
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
        # Таблица уже создана в PostgreSQL инициализации
        pass

    def save_activity(self, activity: UserActivity):
        """Сохранить активность пользователя"""
        try:
            self.db.execute_query('''
                INSERT INTO user_activity 
                (user_id, last_message_time, last_proactive_time, message_count, timezone_offset, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    last_message_time = EXCLUDED.last_message_time,
                    last_proactive_time = EXCLUDED.last_proactive_time,
                    message_count = EXCLUDED.message_count,
                    timezone_offset = EXCLUDED.timezone_offset,
                    updated_at = EXCLUDED.updated_at
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
                'SELECT last_message_time, last_proactive_time, message_count, timezone_offset FROM user_activity WHERE user_id = %s',
                (user_id,)
            )

            if result:
                return UserActivity(
                    user_id=user_id,
                    last_message_time=result["last_message_time"],
                    last_proactive_time=result["last_proactive_time"],
                    message_count=result["message_count"] or 0,
                    timezone_offset=result["timezone_offset"] or 0
                )
            return None
        except Exception as e:
            print(f"❌ Error getting activity: {e}")
            return None