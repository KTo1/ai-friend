from dataclasses import dataclass
import os


@dataclass
class MessageLimitConfig:
    """Конфигурация лимитов сообщений для пользователя"""
    max_message_length: int = 100
    max_context_messages: int = 3
    max_context_length: int = 1200

    @classmethod
    def from_env(cls) -> 'MessageLimitConfig':
        """Создать конфигурацию из переменных окружения"""
        return cls(
            max_message_length=int(os.getenv("DEFAULT_MAX_MESSAGE_LENGTH", "2000")),
            max_context_messages=int(os.getenv("DEFAULT_MAX_CONTEXT_MESSAGES", "10")),
            max_context_length=int(os.getenv("DEFAULT_MAX_CONTEXT_LENGTH", "4000"))
        )


@dataclass
class UserMessageLimit:
    """Персональные лимиты сообщений пользователя"""
    user_id: int
    config: MessageLimitConfig
    total_messages_processed: int = 0
    total_characters_processed: int = 0
    average_message_length: float = 0.0
    rejected_messages_count: int = 0  # Счетчик отклоненных сообщений

    def update_stats(self, message_length: int, was_rejected: bool = False):
        """Обновить статистику сообщений"""
        if not was_rejected:
            self.total_messages_processed += 1
            self.total_characters_processed += message_length
            self.average_message_length = self.total_characters_processed / self.total_messages_processed
        else:
            self.rejected_messages_count += 1

    def get_stats(self) -> dict:
        """Получить статистику пользователя"""
        return {
            'total_messages': self.total_messages_processed,
            'total_characters': self.total_characters_processed,
            'average_length': round(self.average_message_length, 2),
            'rejected_messages': self.rejected_messages_count,
            'limits': {
                'max_message_length': self.config.max_message_length,
                'max_context_messages': self.config.max_context_messages,
                'max_context_length': self.config.max_context_length
            }
        }