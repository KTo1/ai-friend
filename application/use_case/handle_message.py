import asyncio
from domain.service.context_service import ContextService
from domain.interfaces.ai_client import AIClientInterface
from domain.service.message_limit_service import MessageLimitService
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.monitoring.metrics import metrics_collector, Timer
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class HandleMessageUseCase:
    def __init__(self, conversation_repository: ConversationRepository, ai_client: AIClientInterface,  message_limit_service: MessageLimitService):
        self.conversation_repo = conversation_repository
        self.ai_client = ai_client
        self.message_limit_service = message_limit_service
        self.context_service = ContextService()
        self.logger = StructuredLogger("handle_message_uc")

    @trace_span("usecase.handle_message", attributes={"component": "application"})
    async def execute(self, user_id: int, message: str, system_prompt: str) -> str:
        """Обработать сообщение пользователя (асинхронно)"""
        try:
            metrics_collector.record_message_received("text")

            import time
            start_time = time.time()

            # Сохраняем сообщение пользователя
            self.conversation_repo.save_message(user_id, "user", message)

            message_limits = self.message_limit_service.get_user_limits(user_id)

            # Получаем контекст разговора
            context_messages = self.conversation_repo.get_conversation_context(user_id, message_limits.config.max_context_messages) or []

            metrics_collector.record_conversation_length(len(context_messages))

            # Подготавливаем сообщения для AI
            messages = self.context_service.prepare_messages_for_ai(
                system_prompt, context_messages, message
            )

            # БЕЗОПАСНАЯ генерация ответа (теперь с правильными таймаутами)
            try:
                bot_response = await self.ai_client.generate_response_safe(messages)
            except Exception as e:
                self.logger.error(f"AI response error: {e}")
                bot_response = "Извини, что-то пошло не так... Попробуй написать еще раз! 🔄"

            # Сохраняем ответ бота
            self.conversation_repo.save_message(user_id, "assistant", bot_response)

            duration = time.time() - start_time
            metrics_collector.record_processing_time("message_processing", duration)
            metrics_collector.record_message_processed("success")

            self.logger.info(
                "Message processed successfully",
                extra={
                    'user_id': user_id,
                    'message_length': len(message),
                    'response_length': len(bot_response),
                    'duration_ms': duration * 1000
                }
            )

            return bot_response

        except Exception as e:
            metrics_collector.record_message_processed("error")
            self.logger.error(
                f"Error processing message: {e}",
                extra={'user_id': user_id, 'operation': 'handle_message'}
            )
            # Fallback на случай если всё сломалось
            return "Привет! Как твои дела? 😊"