# 📄 application/use_case/manage_user_limits.py
from typing import Dict, Any, Tuple, List
from domain.entity.user_stats import UserStats
from domain.entity.tariff_plan import TariffPlan
from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageUserLimitsUseCase:
    """Use case для управления статистикой пользователя (не лимитами!)"""

    def __init__(self, user_stats_repository: UserStatsRepository):
        self.user_stats_repo = user_stats_repository
        self.logger = StructuredLogger("manage_user_limits_uc")

    @trace_span("usecase.get_user_stats", attributes={"component": "application"})
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику пользователя"""
        stats = self.user_stats_repo.get_user_stats(user_id)

        if not stats:
            return {
                'total_messages': 0,
                'total_characters': 0,
                'average_length': 0.0,
                'rejected_messages': 0,
                'rate_limit_hits': 0,
                'last_message_at': None
            }

        return {
            'total_messages': stats.total_messages_processed,
            'total_characters': stats.total_characters_processed,
            'average_length': round(stats.average_message_length, 2),
            'rejected_messages': stats.total_messages_rejected,
            'rate_limit_hits': stats.total_rate_limit_hits,
            'last_message_at': stats.last_message_at
        }

    @trace_span("usecase.get_tariff_limits_info", attributes={"component": "application"})
    def get_tariff_limits_info(self, tariff: TariffPlan) -> Dict[str, Any]:
        """Получить информацию о лимитах тарифа"""
        return {
            'rate_limits': {
                'messages_per_minute': tariff.rate_limits.messages_per_minute,
                'messages_per_hour': tariff.rate_limits.messages_per_hour,
                'messages_per_day': tariff.rate_limits.messages_per_day
            },
            'message_limits': {
                'max_message_length': tariff.message_limits.max_message_length,
                'max_context_messages': tariff.message_limits.max_context_messages,
            }
        }

    @trace_span("usecase.update_user_stats", attributes={"component": "application"})
    def update_user_stats(self, user_id: int, **stats_data) -> bool:
        """Обновить статистику пользователя"""
        try:
            stats = self.user_stats_repo.get_user_stats(user_id)
            if not stats:
                stats = UserStats(user_id=user_id)

            # Здесь можно добавить логику обновления статистики
            # Например, если нужно обновить какие-то поля вручную

            self.user_stats_repo.save_user_stats(stats)
            return True
        except Exception as e:
            self.logger.error(f"Error updating user stats for {user_id}: {e}")
            return False