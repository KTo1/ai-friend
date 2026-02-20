from typing import Optional, List
from datetime import datetime
from domain.entity.user import User
from infrastructure.database.database import Database


class UserRepository:
    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы пользователей (уже выполнена в PostgreSQL)"""
        pass

    def save_user(self, user: User):
        """Сохранить пользователя"""
        self.db.execute_query('''
            INSERT INTO users 
            (user_id, username, first_name, last_name, current_character_id, is_admin, is_blocked, 
             blocked_reason, blocked_at, blocked_by, last_seen, last_proactive_sent_at, proactive_missed_count, proactive_enabled, bot_blocked_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                current_character_id = EXCLUDED.current_character_id, 
                is_admin = EXCLUDED.is_admin,
                is_blocked = EXCLUDED.is_blocked,
                blocked_reason = EXCLUDED.blocked_reason,
                blocked_at = EXCLUDED.blocked_at,
                blocked_by = EXCLUDED.blocked_by,
                last_seen = EXCLUDED.last_seen,
                last_proactive_sent_at = EXCLUDED.last_proactive_sent_at,
                proactive_missed_count = EXCLUDED.proactive_missed_count,
                proactive_enabled = EXCLUDED.proactive_enabled,
                bot_blocked_at = EXCLUDED.bot_blocked_at
        ''', (
            user.user_id,
            user.username,
            user.first_name,
            user.last_name,
            user.current_character_id,
            user.is_admin,
            user.is_blocked,
            user.blocked_reason,
            user.blocked_at,
            user.blocked_by,
            user.last_seen,
            user.last_proactive_sent_at,
            user.proactive_missed_count,
            user.proactive_enabled,
            user.bot_blocked_at
        ))

    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = self.db.fetch_one(
            '''SELECT user_id, username, first_name, last_name, current_character_id, is_admin, 
                      is_blocked, blocked_reason, blocked_at, blocked_by, 
                      created_at, last_seen, last_proactive_sent_at, proactive_missed_count, proactive_enabled, bot_blocked_at 
               FROM users WHERE user_id = %s''',
            (user_id,)
        )

        if result:
            return User(
                user_id=result['user_id'],
                username=result['username'],
                first_name=result['first_name'],
                last_name=result['last_name'],
                current_character_id=result['current_character_id'],
                is_admin=bool(result['is_admin']),
                is_blocked=bool(result['is_blocked']),
                blocked_reason=result['blocked_reason'],
                blocked_at=self._parse_datetime(result['blocked_at']),
                blocked_by=result['blocked_by'],
                created_at=self._parse_datetime(result['created_at']),
                last_seen=self._parse_datetime(result['last_seen']),
                last_proactive_sent_at=result['last_proactive_sent_at'],
                proactive_missed_count=result['proactive_missed_count'] or 0,
                proactive_enabled=result['proactive_enabled'],
                bot_blocked_at=result['bot_blocked_at']
            )
        return None

    def get_all_users(self) -> List[User]:
        """Получить всех пользователей"""
        results = self.db.fetch_all(
            '''SELECT user_id, username, first_name, last_name, current_character_id, is_admin,
                      is_blocked, blocked_reason, blocked_at, blocked_by,
                      created_at, last_seen, last_proactive_sent_at, proactive_missed_count, proactive_enabled, bot_blocked_at  
               FROM users ORDER BY created_at DESC'''
        )

        users = []
        for result in results:
            users.append(User(
                user_id=result['user_id'],
                username=result['username'],
                first_name=result['first_name'],
                last_name=result['last_name'],
                current_character_id=result['current_character_id'],
                is_admin=bool(result['is_admin']),
                is_blocked=bool(result['is_blocked']),
                blocked_reason=result['blocked_reason'],
                blocked_at=self._parse_datetime(result['blocked_at']),
                blocked_by=result['blocked_by'],
                created_at=self._parse_datetime(result['created_at']),
                last_seen=self._parse_datetime(result['last_seen']),
                last_proactive_sent_at=result['last_proactive_sent_at'],
                proactive_missed_count=result['proactive_missed_count'] or 0,
                proactive_enabled=result['proactive_enabled'],
                bot_blocked_at=result['bot_blocked_at']
            ))

        return users

    def get_blocked_users(self) -> List[User]:
        """Получить всех заблокированных пользователей"""
        results = self.db.fetch_all(
            '''SELECT user_id, username, first_name, last_name, is_admin,
                      is_blocked, blocked_reason, blocked_at, blocked_by,
                      created_at, last_seen, last_proactive_sent_at, proactive_missed_count, proactive_enabled, bot_blocked_at 
               FROM users WHERE is_blocked = TRUE ORDER BY blocked_at DESC'''
        )

        blocked_users = []
        for result in results:
            blocked_users.append(User(
                user_id=result['user_id'],
                username=result['username'],
                first_name=result['first_name'],
                last_name=result['last_name'],
                is_admin=bool(result['is_admin']),
                is_blocked=bool(result['is_blocked']),
                blocked_reason=result['blocked_reason'],
                blocked_at=self._parse_datetime(result['blocked_at']),
                blocked_by=result['blocked_by'],
                created_at=self._parse_datetime(result['created_at']),
                last_seen=self._parse_datetime(result['last_seen']),
                last_proactive_sent_at=result['last_proactive_sent_at'],
                proactive_missed_count=result['proactive_missed_count'] or 0,
                proactive_enabled=result['proactive_enabled'],
                bot_blocked_at=result['bot_blocked_at']
            ))

        return blocked_users

    def update_last_seen(self, user_id: int):
        """Обновить время последней активности пользователя"""
        self.db.execute_query(
            'UPDATE users SET last_seen = %s WHERE user_id = %s',
            (datetime.now(), user_id)
        )

    def delete_user(self, user_id: int):
        """Удалить пользователя"""
        self.db.execute_query('DELETE FROM users WHERE user_id = %s', (user_id,))

    def get_users_for_proactive(self) -> List[User]:
        """Возвращает пользователей с включёнными проактивными и не заблокированных."""
        results = self.db.fetch_all("""
            SELECT user_id, username, first_name, last_name, current_character_id,
                   is_admin, is_blocked, blocked_reason, blocked_at, blocked_by,
                   created_at, last_seen,
                   last_proactive_sent_at, proactive_missed_count, proactive_enabled, bot_blocked_at
            FROM users
            WHERE is_blocked = FALSE AND proactive_enabled = TRUE AND current_character_id IS NOT NULL
            ORDER BY user_id
        """)
        users = []
        for result in results:
            users.append(User(
                user_id=result['user_id'],
                username=result['username'],
                first_name=result['first_name'],
                last_name=result['last_name'],
                current_character_id=result['current_character_id'],
                is_admin=bool(result['is_admin']),
                is_blocked=bool(result['is_blocked']),
                blocked_reason=result['blocked_reason'],
                blocked_at=self._parse_datetime(result['blocked_at']),
                blocked_by=result['blocked_by'],
                created_at=self._parse_datetime(result['created_at']),
                last_seen=self._parse_datetime(result['last_seen']),
                last_proactive_sent_at=result['last_proactive_sent_at'],
                proactive_missed_count=result['proactive_missed_count'] or 0,
                proactive_enabled=bool(result['proactive_enabled']),
                bot_blocked_at=result['bot_blocked_at']
            ))
        return users

    def _parse_datetime(self, dt_value) -> datetime:
        """Парсинг datetime из различных форматов"""
        if dt_value is None:
            return datetime.now()

        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, str):
            try:
                # PostgreSQL возвращает datetime в формате ISO
                return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
            except Exception:
                return datetime.now()

        return datetime.now()