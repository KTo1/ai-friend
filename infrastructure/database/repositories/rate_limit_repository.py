# infrastructure/database/repositories/rate_limit_repository.py
import threading
from datetime import datetime, timedelta
from domain.entity.rate_limit_state import RateLimitState
from domain.entity.user import UserLimits


class RateLimitRepository:
    def __init__(self, database):
        self.db = database
        self._lock = threading.Lock()  # 🔒 Защита от race conditions
        self._init_table()

    def _init_table(self):
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS rate_limit_state (
                user_id INTEGER PRIMARY KEY,
                minute_window_start TIMESTAMP,
                minute_count INTEGER DEFAULT 0,
                hour_window_start TIMESTAMP,
                hour_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def check_and_increment(self, user_id: int, limits: UserLimits) -> dict:
        """Атомарная проверка и инкремент rate limits"""
        with self._lock:  # 🔒 Гарантируем атомарность
            now = datetime.now()
            state = self._get_or_create_state(user_id, now)

            # Проверяем и сбрасываем минутное окно
            if now - state.minute_window_start > timedelta(minutes=1):
                state.minute_count = 0
                state.minute_window_start = now

            # Проверяем и сбрасываем часовое окно
            if now - state.hour_window_start > timedelta(hours=1):
                state.hour_count = 0
                state.hour_window_start = now

            # Проверяем лимиты
            minute_allowed = state.minute_count < limits.messages_per_minute
            hour_allowed = state.hour_count < limits.messages_per_hour
            allowed = minute_allowed and hour_allowed

            # Инкрементируем если разрешено
            if allowed:
                state.minute_count += 1
                state.hour_count += 1
                state.last_updated = now
                self._save_state(state)

            return {
                "allowed": allowed,
                "minute_remaining": max(0, limits.messages_per_minute - state.minute_count),
                "hour_remaining": max(0, limits.messages_per_hour - state.hour_count),
                "minute_count": state.minute_count,
                "hour_count": state.hour_count
            }

    def _get_or_create_state(self, user_id: int, now: datetime) -> RateLimitState:
        result = self.db.fetch_one(
            'SELECT minute_window_start, minute_count, hour_window_start, hour_count, last_updated '
            'FROM rate_limit_state WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return RateLimitState(
                user_id=user_id,
                minute_window_start=datetime.fromisoformat(result[0]),
                minute_count=result[1],
                hour_window_start=datetime.fromisoformat(result[2]),
                hour_count=result[3],
                last_updated=datetime.fromisoformat(result[4])
            )
        else:
            # Создаем новое состояние
            new_state = RateLimitState(
                user_id=user_id,
                minute_window_start=now,
                hour_window_start=now
            )
            self._save_state(new_state)
            return new_state

    def _save_state(self, state: RateLimitState):
        self.db.execute_query('''
            INSERT OR REPLACE INTO rate_limit_state 
            (user_id, minute_window_start, minute_count, hour_window_start, hour_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            state.user_id,
            state.minute_window_start.isoformat(),
            state.minute_count,
            state.hour_window_start.isoformat(),
            state.hour_count,
            state.last_updated.isoformat()
        ))