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
            'SELECT name, age, interests, mood, last_active FROM user_profiles WHERE user_id = %s',
            (user_id,)
        )

        if result:
            return UserProfile(
                user_id=user_id,
                name=result["name"],
                age=result["age"],
                interests=result["interests"],
                mood=result["mood"],
                last_active=result["last_active"]
            )
        return None

    def save_profile(self, profile: UserProfile):
        """Сохранить профиль пользователя"""
        existing = self.db.fetch_one('SELECT 1 FROM user_profiles WHERE user_id = %s', (profile.user_id,))

        if existing:
            self.db.execute_query('''
                UPDATE user_profiles 
                SET name = %s, age = %s, interests = %s, mood = %s, last_active = %s
                WHERE user_id = %s
            ''', (profile.name, profile.age, profile.interests, profile.mood, profile.last_active, profile.user_id))
        else:
            self.db.execute_query('''
                INSERT INTO user_profiles (user_id, name, age, interests, mood, last_active)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (profile.user_id, profile.name, profile.age, profile.interests, profile.mood, profile.last_active))