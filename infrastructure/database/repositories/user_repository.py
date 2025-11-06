from typing import Optional, List
from datetime import datetime
from domain.entity.user import User
from infrastructure.database.database import Database


class UserRepository:
    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы пользователей с полем is_admin"""
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def save_user(self, user: User):
        """Сохранить пользователя"""
        self.db.execute_query('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, is_admin, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user.user_id,
            user.username,
            user.first_name,
            user.last_name,
            user.is_admin,
            user.last_seen
        ))

    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = self.db.fetch_one(
            'SELECT user_id, username, first_name, last_name, is_admin, created_at, last_seen FROM users WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return User(
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                created_at=self._parse_datetime(result[5]),
                last_seen=self._parse_datetime(result[6])
            )
        return None

    def get_all_users(self) -> List[User]:
        """Получить всех пользователей"""
        results = self.db.fetch_all(
            'SELECT user_id, username, first_name, last_name, is_admin, created_at, last_seen FROM users ORDER BY created_at DESC'
        )

        users = []
        for result in results:
            users.append(User(
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                created_at=self._parse_datetime(result[5]),
                last_seen=self._parse_datetime(result[6])
            ))

        return users

    def get_admin_users(self) -> List[User]:
        """Получить всех администраторов"""
        results = self.db.fetch_all(
            'SELECT user_id, username, first_name, last_name, is_admin, created_at, last_seen FROM users WHERE is_admin = TRUE ORDER BY created_at DESC'
        )

        admins = []
        for result in results:
            admins.append(User(
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                is_admin=bool(result[4]),
                created_at=self._parse_datetime(result[5]),
                last_seen=self._parse_datetime(result[6])
            ))

        return admins

    def update_last_seen(self, user_id: int):
        """Обновить время последней активности пользователя"""
        from datetime import datetime
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