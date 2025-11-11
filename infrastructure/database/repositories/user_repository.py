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
            (user_id, username, first_name, last_name, is_admin, is_blocked, 
             blocked_reason, blocked_at, blocked_by, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                is_admin = EXCLUDED.is_admin,
                is_blocked = EXCLUDED.is_blocked,
                blocked_reason = EXCLUDED.blocked_reason,
                blocked_at = EXCLUDED.blocked_at,
                blocked_by = EXCLUDED.blocked_by,
                last_seen = EXCLUDED.last_seen
        ''', (
            user.user_id,
            user.username,
            user.first_name,
            user.last_name,
            user.is_admin,
            user.is_blocked,
            user.blocked_reason,
            user.blocked_at,
            user.blocked_by,
            user.last_seen
        ))

    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = self.db.fetch_one(
            '''SELECT user_id, username, first_name, last_name, is_admin, 
                      is_blocked, blocked_reason, blocked_at, blocked_by, 
                      created_at, last_seen 
               FROM users WHERE user_id = %s''',
            (user_id,)
        )

        if result:
            return User(
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
                last_seen=self._parse_datetime(result['last_seen'])
            )
        return None

    def get_all_users(self) -> List[User]:
        """Получить всех пользователей"""
        results = self.db.fetch_all(
            '''SELECT user_id, username, first_name, last_name, is_admin,
                      is_blocked, blocked_reason, blocked_at, blocked_by,
                      created_at, last_seen 
               FROM users ORDER BY created_at DESC'''
        )

        users = []
        for result in results:
            users.append(User(
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
                last_seen=self._parse_datetime(result['last_seen'])
            ))

        return users

    def get_admin_users(self) -> List[User]:
        """Получить всех администраторов"""
        results = self.db.fetch_all(
            '''SELECT user_id, username, first_name, last_name, is_admin,
                      is_blocked, blocked_reason, blocked_at, blocked_by,
                      created_at, last_seen 
               FROM users WHERE is_admin = TRUE ORDER BY created_at DESC'''
        )

        admins = []
        for result in results:
            admins.append(User(
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
                last_seen=self._parse_datetime(result['last_seen'])
            ))

        return admins

    def get_blocked_users(self) -> List[User]:
        """Получить всех заблокированных пользователей"""
        results = self.db.fetch_all(
            '''SELECT user_id, username, first_name, last_name, is_admin,
                      is_blocked, blocked_reason, blocked_at, blocked_by,
                      created_at, last_seen 
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
                last_seen=self._parse_datetime(result['last_seen'])
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