from typing import Dict, Any, Tuple, List
from domain.entity.user_limits import UserLimits, RateLimitConfig, MessageLimitConfig
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageUserLimitsUseCase:
    """Use case для управления ВСЕМИ лимитами пользователя"""

    def __init__(self, rate_limit_service, message_limit_service):
        self.rate_limit_service = rate_limit_service
        self.message_limit_service = message_limit_service
        self.logger = StructuredLogger("manage_user_limits_uc")

    @trace_span("usecase.get_all_limits", attributes={"component": "application"})
    def get_all_limits(self, user_id: int) -> UserLimits:
        """Получить ВСЕ лимиты пользователя"""
        try:
            # Получаем рейт-лимиты через публичные методы
            rate_limits = self.rate_limit_service.get_user_limits_config(user_id)

            # Получаем лимиты сообщений через публичные методы
            message_limits = self.message_limit_service.get_user_limits_config(user_id)

            return UserLimits(
                user_id=user_id,
                rate_limits=rate_limits,
                message_limits=message_limits
            )

        except Exception as e:
            self.logger.error(f"Error getting all limits for user {user_id}: {e}")
            return UserLimits.create_default(user_id)

    @trace_span("usecase.update_limits", attributes={"component": "application"})
    def update_limits(self, user_id: int, **limits) -> Tuple[bool, str]:
        """
        Обновить любые лимиты пользователя
        """
        try:
            # Разделяем лимиты по типам
            rate_limits = {}
            message_limits = {}

            rate_limit_fields = ['messages_per_minute', 'messages_per_hour', 'messages_per_day']
            message_limit_fields = ['max_message_length', 'max_context_messages', 'max_context_length']

            for key, value in limits.items():
                if key in rate_limit_fields:
                    rate_limits[key] = value
                elif key in message_limit_fields:
                    message_limits[key] = value
                else:
                    self.logger.warning(f"Unknown limit field: {key}")

            # Обновляем рейт-лимиты через публичные методы
            if rate_limits:
                success = self.rate_limit_service.update_user_limits_config(user_id, **rate_limits)
                if not success:
                    return False, f"❌ Ошибка при обновлении рейт-лимитов"

            # Обновляем лимиты сообщений через публичные методы
            if message_limits:
                success = self.message_limit_service.update_user_limits_config(user_id, **message_limits)
                if not success:
                    return False, f"❌ Ошибка при обновлении лимитов сообщений"

            # Логируем изменения
            changes = []
            if rate_limits:
                changes.append(f"рейт-лимиты: {rate_limits}")
            if message_limits:
                changes.append(f"лимиты сообщений: {message_limits}")

            self.logger.info(
                f"Updated limits for user {user_id}",
                extra={'user_id': user_id, 'changes': changes}
            )

            return True, f"✅ Лимиты пользователя {user_id} обновлены: {', '.join(changes)}"

        except Exception as e:
            self.logger.error(f"Error updating limits for user {user_id}: {e}")
            return False, f"❌ Ошибка при обновлении лимитов: {str(e)}"

    @trace_span("usecase.reset_all_limits", attributes={"component": "application"})
    def reset_all_limits(self, user_id: int) -> Tuple[bool, str]:
        """Сбросить ВСЕ лимиты пользователя к значениям по умолчанию"""
        try:
            # Сбрасываем рейт-лимиты
            self.rate_limit_service.reset_user_limits(user_id)

            # Сбрасываем лимиты сообщений
            self.message_limit_service.reset_user_limits(user_id)

            self.logger.info(f"All limits reset for user {user_id}")
            return True, f"✅ Все лимиты пользователя {user_id} сброшены к значениям по умолчанию"

        except Exception as e:
            self.logger.error(f"Error resetting limits for user {user_id}: {e}")
            return False, f"❌ Ошибка при сбросе лимитов: {str(e)}"

    def get_available_limits_info(self) -> str:
        """Получить информацию о доступных лимитах"""
        info = """
📊 **Доступные лимиты для настройки:**

🕒 **Рейт-лимиты (сообщения в единицу времени):**
• `messages_per_minute` - сообщений в минуту
• `messages_per_hour` - сообщений в час  
• `messages_per_day` - сообщений в день

📏 **Лимиты сообщений (размеры и объем):**
• `max_message_length` - макс. длина одного сообщения (символов)
• `max_context_messages` - макс. сообщений в истории
• `max_context_length` - макс. длина всего контекста (символов)

💡 **Примеры использования:**
`/admin_set_limits 123456789 messages_per_hour=50 max_message_length=3000`
`/admin_set_limits 123456789 max_context_messages=20 messages_per_day=200`
        """
        return info