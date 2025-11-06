from typing import Optional, List
from datetime import datetime
from domain.entity.user import User
from infrastructure.database.database import Database


class UserRepository:
    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы пользователей с полями блокировки"""
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                is_blocked BOOLEAN DEFAULT FALSE,
                blocked_reason TEXT,
                blocked_at TIMESTAMP,
                blocked_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def save_user(self, user: User):
        """Сохранить пользователя"""
        self.db.execute_query('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, is_admin, is_blocked, 
             blocked_reason, blocked_at, blocked_by, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
               FROM users WHERE user_id = ?''',
            (user_id,)
        )

        if result:
            return User(
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                is_blocked=bool(result[5]),
                blocked_reason=result[6],
                blocked_at=self._parse_datetime(result[7]),
                blocked_by=result[8],
                created_at=self._parse_datetime(result[9]),
                last_seen=self._parse_datetime(result[10])
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
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                is_blocked=bool(result[5]),
                blocked_reason=result[6],
                blocked_at=self._parse_datetime(result[7]),
                blocked_by=result[8],
                created_at=self._parse_datetime(result[9]),
                last_seen=self._parse_datetime(result[10])
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
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                is_blocked=bool(result[5]),
                blocked_reason=result[6],
                blocked_at=self._parse_datetime(result[7]),
                blocked_by=result[8],
                created_at=self._parse_datetime(result[9]),
                last_seen=self._parse_datetime(result[10])
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
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                is_blocked=bool(result[5]),
                blocked_reason=result[6],
                blocked_at=self._parse_datetime(result[7]),
                blocked_by=result[8],
                created_at=self._parse_datetime(result[9]),
                last_seen=self._parse_datetime(result[10])
            ))

        return blocked_users

    def update_last_seen(self, user_id: int):
        """Обновить время последней активности пользователя"""
        self.db.execute_query(
            'UPDATE users SET last_seen = ? WHERE user_id = ?',
            (datetime.now(), user_id)
        )

    def delete_user(self, user_id: int):
        """Удалить пользователя"""
        self.db.execute_query('DELETE FROM users WHERE user_id = ?', (user_id,))

    def _parse_datetime(self, dt_value) -> datetime:
        """Парсинг datetime из различных форматов"""
        if dt_value is None:
            return datetime.now()

        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, str):
            try:
                # Пробуем разные форматы дат
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f',
                            '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                            '%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S.%f%z']:
                    try:
                        return datetime.strptime(dt_value, fmt)
                    except ValueError:
                        continue

                # Если ни один формат не подошел, возвращаем текущее время
                return datetime.now()
            except Exception:
                return datetime.now()

        # Если непонятный тип, возвращаем текущее время
        return datetime.now()