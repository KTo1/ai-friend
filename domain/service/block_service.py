from typing import List, Dict, Optional, Tuple
from datetime import datetime
from domain.entity.user import User
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.monitoring.logging import StructuredLogger


class BlockService:
    """Сервис для управления блокировками пользователей"""

    def __init__(self, user_repository: UserRepository):
        self.user_repo = user_repository
        self.logger = StructuredLogger("block_service")

    def is_user_blocked(self, user_id: int) -> bool:
        """Проверить, заблокирован ли пользователь"""
        user = self.user_repo.get_user(user_id)
        return user and user.is_blocked

    def block_user(self, target_user_id: int, admin_user_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
        """
        Заблокировать пользователя

        Args:
            target_user_id: ID пользователя для блокировки
            admin_user_id: ID администратора, выполняющего блокировку
            reason: Причина блокировки

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        # Проверяем, что администратор существует
        admin_user = self.user_repo.get_user(admin_user_id)
        if not admin_user or not admin_user.is_admin:
            return False, "Только администраторы могут блокировать пользователей"

        # Нельзя блокировать себя
        if target_user_id == admin_user_id:
            return False, "Нельзя заблокировать самого себя"

        # Проверяем целевого пользователя
        target_user = self.user_repo.get_user(target_user_id)
        if not target_user:
            return False, f"Пользователь с ID {target_user_id} не найден"

        # Нельзя блокировать других администраторов
        if target_user.is_admin:
            return False, "Нельзя блокировать других администраторов"

        # Если пользователь уже заблокирован
        if target_user.is_blocked:
            return False, f"Пользователь {target_user_id} уже заблокирован"

        # Выполняем блокировку
        target_user.block_user(admin_user_id, reason)
        self.user_repo.save_user(target_user)

        # Логируем действие
        self.logger.info(
            f"User {target_user_id} blocked by {admin_user_id}",
            extra={
                'admin_user_id': admin_user_id,
                'target_user_id': target_user_id,
                'target_username': target_user.username,
                'reason': reason,
                'operation': 'block_user'
            }
        )

        message = f"✅ Пользователь {target_user_id} заблокирован"
        if reason:
            message += f"\nПричина: {reason}"

        return True, message

    def unblock_user(self, target_user_id: int, admin_user_id: int) -> Tuple[bool, str]:
        """
        Разблокировать пользователя

        Args:
            target_user_id: ID пользователя для разблокировки
            admin_user_id: ID администратора, выполняющего разблокировку

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        # Проверяем, что администратор существует
        admin_user = self.user_repo.get_user(admin_user_id)
        if not admin_user or not admin_user.is_admin:
            return False, "Только администраторы могут разблокировать пользователей"

        # Проверяем целевого пользователя
        target_user = self.user_repo.get_user(target_user_id)
        if not target_user:
            return False, f"Пользователь с ID {target_user_id} не найден"

        # Если пользователь не заблокирован
        if not target_user.is_blocked:
            return False, f"Пользователь {target_user_id} не заблокирован"

        # Выполняем разблокировку
        target_user.unblock_user()
        self.user_repo.save_user(target_user)

        # Логируем действие
        self.logger.info(
            f"User {target_user_id} unblocked by {admin_user_id}",
            extra={
                'admin_user_id': admin_user_id,
                'target_user_id': target_user_id,
                'target_username': target_user.username,
                'operation': 'unblock_user'
            }
        )

        return True, f"✅ Пользователь {target_user_id} разблокирован"

    def get_blocked_users(self) -> List[User]:
        """Получить список заблокированных пользователей"""
        all_users = self.user_repo.get_all_users()
        return [user for user in all_users if user.is_blocked]

    def get_block_info(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о блокировке пользователя"""
        user = self.user_repo.get_user(user_id)

        if not user or not user.is_blocked:
            return None

        blocked_by_user = self.user_repo.get_user(user.blocked_by) if user.blocked_by else None
        blocked_by_name = (
            f"@{blocked_by_user.username}"
            if blocked_by_user and blocked_by_user.username
            else f"ID: {user.blocked_by}"
        ) if user.blocked_by else "Система"

        return {
            'reason': user.blocked_reason,
            'blocked_at': user.blocked_at,
            'blocked_by': user.blocked_by,
            'blocked_by_name': blocked_by_name,
            'blocked_duration': self._get_block_duration(user.blocked_at)
        }

    def _get_block_duration(self, blocked_at: datetime) -> str:
        """Получить продолжительность блокировки в читаемом формате"""
        if not blocked_at:
            return "неизвестно"

        duration = datetime.now() - blocked_at
        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60

        if days > 0:
            return f"{days}д {hours}ч"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"