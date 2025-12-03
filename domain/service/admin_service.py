from typing import List, Dict, Optional
from datetime import datetime, timedelta
from domain.entity.user import User
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.monitoring.logging import StructuredLogger


class AdminService:
    """Сервис для управления администраторами"""

    def __init__(self, user_repository: UserRepository):
        self.user_repo = user_repository
        self.logger = StructuredLogger("admin_service")

        # Список user_id администраторов по умолчанию (из env)
        self._load_default_admins()

    def _load_default_admins(self):
        """Загрузить администраторов по умолчанию из переменных окружения"""
        import os
        admin_ids_str = os.getenv("DEFAULT_ADMIN_IDS", "")
        self.default_admin_ids = []

        if admin_ids_str:
            try:
                self.default_admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(",")]
                self.logger.info(f"Loaded default admin IDs: {self.default_admin_ids}")
            except ValueError as e:
                self.logger.error(f"Error parsing DEFAULT_ADMIN_IDS: {e}")

    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        user = self.user_repo.get_user(user_id)

        if user:
            return user.is_admin

        # Проверяем администраторов по умолчанию
        return user_id in self.default_admin_ids

    def get_admin_users(self) -> List[User]:
        """Получить список всех администраторов"""
        all_users = self._get_all_users()
        return [user for user in all_users if user.is_admin]

    def get_all_users(self) -> List[User]:
        """Получить список всех пользователей"""
        return self._get_all_users()

    def get_user_stats(self) -> Dict:
        """Получить статистику пользователей"""
        users = self._get_all_users()
        total_users = len(users)
        admin_users = len([u for u in users if u.is_admin])
        active_users = len([u for u in users if self._is_user_active(u)])

        return {
            'total_users': total_users,
            'admin_users': admin_users,
            'regular_users': total_users - admin_users,
            'active_users': active_users,
            'inactive_users': total_users - active_users
        }

    def _get_all_users(self) -> List[User]:
        """Получить всех пользователей из репозитория"""
        try:
            return self.user_repo.get_all_users()
        except Exception as e:
            self.logger.error(f"Error getting all users: {e}")
            return []

    def _is_user_active(self, user: User) -> bool:
        """Проверить, активен ли пользователь (был онлайн в последние 7 дней)"""
        try:
            if not user.last_seen:
                return False

            week_ago = datetime.now() - timedelta(days=7)

            # Убедимся, что last_seen - это datetime объект
            if isinstance(user.last_seen, str):
                # Если это строка, попробуем преобразовать
                user.last_seen = self._parse_datetime(user.last_seen)

            return user.last_seen >= week_ago

        except Exception as e:
            self.logger.error(f"Error checking user activity for {user.user_id}: {e}")
            return False

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