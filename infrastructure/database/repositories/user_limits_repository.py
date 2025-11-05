# infrastructure/database/repositories/user_limits_repository.py
from typing import Optional, Dict, Any
from domain.entity.user import UserLimits
from infrastructure.database.database import Database
from datetime import datetime

class UserLimitsRepository:
    def __init__(self, database: Database):
        self.db = database

    def get_user_limits(self, user_id: int) -> Optional[UserLimits]:
        """Получить лимиты пользователя"""
        result = self.db.fetch_one(
            'SELECT max_daily_requests, max_message_length, max_context_messages, '
            'max_tokens_per_request, custom_limits_enabled FROM user_limits WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return UserLimits(
                max_daily_requests=result[0],
                max_message_length=result[1],
                max_context_messages=result[2],
                max_tokens_per_request=result[3],
                custom_limits_enabled=result[4]
            )
        return None

    def set_user_limits(self, user_id: int, limits: UserLimits):
        """Установить лимиты пользователя"""
        self.db.execute_query('''
            INSERT OR REPLACE INTO user_limits 
            (user_id, max_daily_requests, max_message_length, max_context_messages, 
             max_tokens_per_request, custom_limits_enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, limits.max_daily_requests, limits.max_message_length,
              limits.max_context_messages, limits.max_tokens_per_request,
              limits.custom_limits_enabled))

    def get_user_usage_today(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику использования за сегодня"""
        result = self.db.fetch_one(
            'SELECT requests_count, total_tokens_used, total_cost_estimated '
            'FROM user_usage_stats WHERE user_id = ? AND date = DATE("now")',
            (user_id,)
        )

        if result:
            return {
                'requests_count': result[0],
                'total_tokens_used': result[1],
                'total_cost_estimated': result[2]
            }
        return {'requests_count': 0, 'total_tokens_used': 0, 'total_cost_estimated': 0.0}

    def increment_user_usage(self, user_id: int, tokens_used: int, cost: float):
        """Увеличить счетчик использования"""
        today = datetime.now().date()

        # Проверяем существующую запись
        existing = self.db.fetch_one(
            'SELECT 1 FROM user_usage_stats WHERE user_id = ? AND date = ?',
            (user_id, today)
        )

        if existing:
            self.db.execute_query('''
                UPDATE user_usage_stats 
                SET requests_count = requests_count + 1,
                    total_tokens_used = total_tokens_used + ?,
                    total_cost_estimated = total_cost_estimated + ?
                WHERE user_id = ? AND date = ?
            ''', (tokens_used, cost, user_id, today))
        else:
            self.db.execute_query('''
                INSERT INTO user_usage_stats 
                (user_id, date, requests_count, total_tokens_used, total_cost_estimated)
                VALUES (?, ?, 1, ?, ?)
            ''', (user_id, today, tokens_used, cost))

    def ban_user(self, user_id: int):
        """Забанить пользователя"""
        self.db.execute_query(
            'UPDATE users SET is_banned = TRUE WHERE user_id = ?',
            (user_id,)
        )

    def unban_user(self, user_id: int):
        """Разбанить пользователя"""
        self.db.execute_query(
            'UPDATE users SET is_banned = FALSE WHERE user_id = ?',
            (user_id,)
        )

    def deactivate_user(self, user_id: int):
        """Деактивировать пользователя"""
        self.db.execute_query(
            'UPDATE users SET is_active = FALSE WHERE user_id = ?',
            (user_id,)
        )

    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        result = self.db.fetch_one(
            'SELECT 1 FROM admins WHERE user_id = ?',
            (user_id,)
        )
        return result is not None