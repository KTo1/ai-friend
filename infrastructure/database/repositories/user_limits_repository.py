# infrastructure/database/repositories/user_limits_repository.py
from typing import Optional, Dict, Any
from domain.entity.user import UserLimits
from infrastructure.database.database import Database
from datetime import datetime

class UserLimitsRepository:
    def __init__(self, database: Database):
        self.db = database

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

    def check_rate_limits(self, user_id: int) -> Dict[str, any]:
        """Проверить rate limits для пользователя"""
        now = datetime.now()

        # Получаем лимиты пользователя (создаем дефолтные если нет записи)
        user_limits = self.get_user_limits(user_id)
        if not user_limits:
            user_limits = UserLimits()
            self.set_user_limits(user_id, user_limits)
            return {"allowed": True, "minute_remaining": 10, "hour_remaining": 100}

        # Инициализируем временные окна если нужно
        if not user_limits.minute_window_start:
            user_limits.minute_window_start = now
        if not user_limits.hour_window_start:
            user_limits.hour_window_start = now

        # Сброс счетчиков если окно истекло
        if (now - user_limits.minute_window_start).total_seconds() > 60:
            user_limits.minute_count = 0
            user_limits.minute_window_start = now

        if (now - user_limits.hour_window_start).total_seconds() > 3600:
            user_limits.hour_count = 0
            user_limits.hour_window_start = now

        # Проверка лимитов
        minute_remaining = max(0, user_limits.messages_per_minute - user_limits.minute_count)
        hour_remaining = max(0, user_limits.messages_per_hour - user_limits.hour_count)

        allowed = (user_limits.minute_count < user_limits.messages_per_minute and
                   user_limits.hour_count < user_limits.messages_per_hour)

        # Обновляем счетчики если сообщение разрешено
        if allowed:
            user_limits.minute_count += 1
            user_limits.hour_count += 1
            user_limits.updated_at = now
            self.set_user_limits(user_id, user_limits)

        return {
            "allowed": allowed,
            "minute_remaining": minute_remaining,
            "hour_remaining": hour_remaining,
            "minute_count": user_limits.minute_count,
            "hour_count": user_limits.hour_count
        }

    def set_user_limits(self, user_id: int, limits: UserLimits):
        """Установить лимиты пользователя"""
        self.db.execute_query('''
            INSERT OR REPLACE INTO user_limits 
            (user_id, max_daily_requests, max_message_length, max_context_messages, 
             max_tokens_per_request, custom_limits_enabled,
             messages_per_minute, messages_per_hour, minute_window_start, minute_count,
             hour_window_start, hour_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            limits.max_daily_requests,
            limits.max_message_length,
            limits.max_context_messages,
            limits.max_tokens_per_request,
            limits.custom_limits_enabled,
            limits.messages_per_minute,
            limits.messages_per_hour,
            limits.minute_window_start,
            limits.minute_count,
            limits.hour_window_start,
            limits.hour_count,
            limits.updated_at or datetime.now()
        ))

    def get_user_limits(self, user_id: int) -> UserLimits:
        """Получить лимиты пользователя, подставляя значения по умолчанию если нет в БД"""
        result = self.db.fetch_one(
            'SELECT max_daily_requests, max_message_length, max_context_messages, '
            'max_tokens_per_request, custom_limits_enabled, '
            'messages_per_minute, messages_per_hour, minute_window_start, minute_count, '
            'hour_window_start, hour_count, updated_at FROM user_limits WHERE user_id = ?',
            (user_id,)
        )

        if result:
            # Создаем объект с данными из БД
            return UserLimits(
                max_daily_requests=result[0],
                max_message_length=result[1],
                max_context_messages=result[2],
                max_tokens_per_request=result[3],
                custom_limits_enabled=result[4] or False,
                messages_per_minute=result[5],
                messages_per_hour=result[6],
                minute_window_start=datetime.fromisoformat(result[7]) if result[7] else None,
                minute_count=result[8] or 0,
                hour_window_start=datetime.fromisoformat(result[9]) if result[9] else None,
                hour_count=result[10] or 0,
                updated_at=datetime.fromisoformat(result[11]) if result[11] else None
            )

        # Если записи нет - возвращаем дефолтные лимиты
        return None