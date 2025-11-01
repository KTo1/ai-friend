from typing import Optional
from datetime import datetime
from domain.entity.profile import UserProfile
from infrastructure.database.database import Database


class ProfileRepository:
    def __init__(self, database: Database):
        self.db = database

    def get_profile(self, user_id: int) -> Optional[UserProfile]:
        """Получить профиль пользователя"""
        result = self.db.fetch_one(
            'SELECT name, age, interests, mood, last_active FROM user_profiles WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return UserProfile(
                user_id=user_id,
                name=result[0],
                age=result[1],
                interests=result[2],
                mood=result[3],
                last_active=datetime.fromisoformat(result[4]) if result[4] else None
            )
        return None

    def save_profile(self, profile: UserProfile):
        """Сохранить профиль пользователя"""
        existing = self.db.fetch_one('SELECT 1 FROM user_profiles WHERE user_id = ?', (profile.user_id,))

        if existing:
            self.db.execute_query('''
                UPDATE user_profiles 
                SET name = ?, age = ?, interests = ?, mood = ?, last_active = ?
                WHERE user_id = ?
            ''', (profile.name, profile.age, profile.interests, profile.mood, profile.last_active, profile.user_id))
        else:
            self.db.execute_query('''
                INSERT INTO user_profiles (user_id, name, age, interests, mood, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (profile.user_id, profile.name, profile.age, profile.interests, profile.mood, profile.last_active))