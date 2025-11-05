from typing import Dict, Any
from domain.entity.user import UserLimits
from infrastructure.database.repositories.user_limits_repository import UserLimitsRepository
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.monitoring.logging import StructuredLogger

class AdminUseCase:
    def __init__(self, user_repository: UserRepository, user_limits_repository: UserLimitsRepository):
        self.user_repo = user_repository
        self.user_limits_repo = user_limits_repository
        self.logger = StructuredLogger("admin_uc")

    def set_user_limits(self, admin_user_id: int, target_user_id: int, limits: UserLimits) -> bool:
        """Установить лимиты пользователя (только для админов)"""
        if not self.user_limits_repo.is_admin(admin_user_id):
            self.logger.warning(f"Non-admin user {admin_user_id} tried to set limits")
            return False

        self.user_limits_repo.set_user_limits(target_user_id, limits)
        self.logger.info(
            f"Admin {admin_user_id} set limits for user {target_user_id}",
            extra={'limits': limits.__dict__}
        )
        return True

    def ban_user(self, admin_user_id: int, target_user_id: int, reason: str = "") -> bool:
        """Забанить пользователя"""
        if not self.user_limits_repo.is_admin(admin_user_id):
            return False

        self.user_limits_repo.ban_user(target_user_id)
        self.logger.warning(
            f"Admin {admin_user_id} banned user {target_user_id}",
            extra={'reason': reason}
        )
        return True

    def unban_user(self, admin_user_id: int, target_user_id: int) -> bool:
        """Разбанить пользователя"""
        if not self.user_limits_repo.is_admin(admin_user_id):
            return False

        self.user_limits_repo.unban_user(target_user_id)
        self.logger.info(f"Admin {admin_user_id} unbanned user {target_user_id}")
        return True

    def get_user_stats(self, admin_user_id: int, target_user_id: int) -> Dict[str, any]:
        """Получить статистику пользователя"""
        if not self.user_limits_repo.is_admin(admin_user_id):
            return {}

        user = self.user_repo.get_user(target_user_id)
        limits = self.user_limits_repo.get_user_limits(target_user_id)
        usage = self.user_limits_repo.get_user_usage_today(target_user_id)

        return {
            'user_info': {
                'user_id': user.user_id,
                'username': user.username,
                'is_banned': user.is_banned,
                'is_active': user.is_active,
                'created_at': user.created_at
            },
            'limits': limits.__dict__ if limits else {},
            'usage_today': usage,
            'remaining_requests': limits.max_daily_requests - usage['requests_count'] if limits else 0
        }