from typing import List, Dict, Tuple
from domain.service.block_service import BlockService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageBlockUseCase:
    """Use case для управления блокировками пользователей"""

    def __init__(self, block_service: BlockService):
        self.block_service = block_service
        self.logger = StructuredLogger("manage_block_uc")

    @trace_span("usecase.check_user_blocked", attributes={"component": "application"})
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверить, заблокирован ли пользователь"""
        return self.block_service.is_user_blocked(user_id)

    @trace_span("usecase.block_user", attributes={"component": "application"})
    def block_user(self, target_user_id: int, admin_user_id: int, reason: str = None) -> Tuple[bool, str]:
        """
        Заблокировать пользователя

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        return self.block_service.block_user(target_user_id, admin_user_id, reason)

    @trace_span("usecase.unblock_user", attributes={"component": "application"})
    def unblock_user(self, target_user_id: int, admin_user_id: int) -> Tuple[bool, str]:
        """
        Разблокировать пользователя

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        return self.block_service.unblock_user(target_user_id, admin_user_id)

    @trace_span("usecase.get_blocked_list", attributes={"component": "application"})
    def get_blocked_list(self) -> str:
        """Получить список заблокированных пользователей"""
        blocked_users = self.block_service.get_blocked_users()

        if not blocked_users:
            return "🔓 Нет заблокированных пользователей"

        message = "🚫 **Заблокированные пользователи:**\n\n"
        for i, user in enumerate(blocked_users, 1):
            username = f"@{user.username}" if user.username else "без username"
            message += f"{i}. {user.first_name or 'Без имени'} {username} (ID: {user.user_id})\n"

            # Информация о блокировке
            block_info = self.block_service.get_block_info(user.user_id)
            if block_info:
                blocked_at_str = self._format_datetime(user.blocked_at)
                message += f"   🕒 Заблокирован: {blocked_at_str}\n"
                message += f"   👤 Заблокировал: {block_info['blocked_by_name']}\n"
                message += f"   ⏱️ Длительность: {block_info['blocked_duration']}\n"
                if user.blocked_reason:
                    message += f"   📝 Причина: {user.blocked_reason}\n"
            message += "\n"

        return message

    @trace_span("usecase.get_block_info", attributes={"component": "application"})
    def get_block_info(self, user_id: int) -> str:
        """Получить информацию о блокировке пользователя"""
        if not self.block_service.is_user_blocked(user_id):
            return f"ℹ️ Пользователь {user_id} не заблокирован"

        block_info = self.block_service.get_block_info(user_id)
        if not block_info:
            return f"❌ Ошибка при получении информации о блокировке пользователя {user_id}"

        user = self.block_service.user_repo.get_user(user_id)
        username = f"@{user.username}" if user and user.username else "без username"

        message = f"🚫 **Информация о блокировке:**\n\n"
        message += f"• Пользователь: {user.first_name or 'Без имени'} {username} (ID: {user_id})\n"
        message += f"• Заблокирован: {self._format_datetime(user.blocked_at)}\n"
        message += f"• Заблокировал: {block_info['blocked_by_name']}\n"
        message += f"• Длительность блокировки: {block_info['blocked_duration']}\n"

        if block_info['reason']:
            message += f"• Причина: {block_info['reason']}\n"
        else:
            message += "• Причина: не указана\n"

        return message

    def _format_datetime(self, dt_value) -> str:
        """Безопасное форматирование datetime"""
        try:
            if not dt_value:
                return "неизвестно"

            if hasattr(dt_value, 'strftime'):
                return dt_value.strftime('%d.%m.%Y %H:%M')
            else:
                return str(dt_value)

        except Exception as e:
            self.logger.debug(f"Error formatting datetime {dt_value}: {e}")
            return "неизвестно"