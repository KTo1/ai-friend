from typing import Optional
from domain.entity.user import User
from infrastructure.database.database import Database


class UserRepository:
    def __init__(self, database: Database):
        self.db = database

    def save_user(self, user: User):
        """Сохранить пользователя"""
        self.db.execute_query('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user.user_id, user.username, user.first_name, user.last_name))

    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = self.db.fetch_one(
            'SELECT user_id, username, first_name, last_name, created_at FROM users WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return User(
                user_id=result[0],
                username=result[1],
                first_name=result[2],
                last_name=result[3],
                created_at=result[4]
            )
        return None