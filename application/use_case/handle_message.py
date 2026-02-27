import time

import asyncio

from domain.service.context_service import ContextService
from domain.interfaces.ai_client import AIClientInterface

from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.database.repositories.character_repository import CharacterRepository

from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger

from application.use_case.manage_summary import ManageSummaryUseCase
from application.use_case.manage_rag import ManageRAGUseCase
from application.use_case.manage_profile import ManageProfileUseCase


class HandleMessageUseCase:
    def __init__(self, conversation_repository: ConversationRepository,
                 character_repository: CharacterRepository, ai_client: AIClientInterface,
                 manage_summary_uc: ManageSummaryUseCase, manage_rag_uc: ManageRAGUseCase, manage_profile_uc: ManageProfileUseCase):
        self.conversation_repo = conversation_repository
        self.character_repo = character_repository
        self.ai_client = ai_client
        self.context_service = ContextService()
        self.manage_summary_uc = manage_summary_uc
        self.manage_rag_uc = manage_rag_uc
        self.manage_profile_uc = manage_profile_uc
        self.logger = StructuredLogger("handle_message_uc")


    @trace_span("usecase.handle_message", attributes={"component": "application"})
    async def execute(self, user_id: int, character_id: int, message: str, max_context_messages: int = 10) -> str:
        """Обработать сообщение пользователя (асинхронно)"""
        try:
            metrics_collector.record_message_received("text")
            start_time = time.time()

            # Получаем персонажа для его системного промпта
            character = self.character_repo.get_character(character_id)
            if not character:
                self.logger.error(f'Character {character_id} not found for user {user_id}')
                return 'Извини, что-то пошло не так... Персонаж не найден! 🔄'

            # Сохраняем сообщение пользователя с учетом лимита контекста
            self.conversation_repo.save_message(
                user_id,
                character_id,
                "user",
                message
            )

            # Получаем контекст разговора с учетом лимита из тарифа
            context_messages = self.conversation_repo.get_conversation_context(
                user_id,
                character_id,
                max_context_messages=max_context_messages
            ) or []

            metrics_collector.record_conversation_length(len(context_messages))

            # Асинхронно запускаем генерацию суммаризаций до ответа бота (не блокируя ответ)
            asyncio.create_task(
                self.manage_summary_uc.check_and_update_summaries(
                    user_id, character.id, character.name, context_messages
                )
            )

            # Извлекаем и сохраняем воспоминания (асинхронно)
            asyncio.create_task(
                self.manage_rag_uc.extract_and_save_memories(user_id, character.id, message)
            )

            # Получаем релевантные воспоминания для текущего сообщения
            rag_context = await self.manage_rag_uc.prepare_rag_context(
                user_id, character.id, message
            )

            # Получаем релевантные воспоминания для текущего сообщения
            recap_context = self.manage_summary_uc.get_summary_context(
                user_id, character.id
            )

            profile_data = await self.manage_profile_uc.extract_and_update_profile(user_id, message, character)

            # Подготавливаем сообщения для AI
            enhanced_system_prompt = (f"""СИСТЕМНЫЙ ПРОМТП, ПОВЕДЕНИЕ ПЕРСОНАЖА: {character.system_prompt}\n\n 
                                      Текущее состояние сцены (recap) — обязательно учитывай каждое слово перед каждым ответом: {recap_context} \n\n
                                      ИЗВЛЕЧЕННЫЕ ВОСПОМИНАНИЯ, используй их в разговоре: {rag_context} \n\n
                                      ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ, используй его в разговоре, если каких-то данных нет (параметр = None), то в зависимости от контекста уточняй их:  {profile_data} \n\n""")
            messages = self.context_service.prepare_messages_for_ai(
                enhanced_system_prompt, context_messages, message
            )

            # БЕЗОПАСНАЯ генерация ответа
            try:
                bot_response = await self.ai_client.generate_response_safe(messages)
            except Exception as e:
                self.logger.error(f"AI response error: {e}")
                bot_response = "Извини, что-то пошло не так... Попробуй написать еще раз! 🔄"

            # Сохраняем ответ бота с учетом лимита контекста
            self.conversation_repo.save_message(
                user_id,
                character.id,
                "assistant",
                bot_response
            )

            # Асинхронно запускаем генерацию суммаризаций уже после ответа бота (не блокируя ответ)
            context_messages.append({'role': 'assistant', 'content': bot_response})
            asyncio.create_task(
                self.manage_summary_uc.check_and_update_summaries(
                    user_id, character.id, character.name, context_messages
                )
            )

            duration = time.time() - start_time
            metrics_collector.record_processing_time("message_processing", duration)
            metrics_collector.record_message_processed("success")

            self.logger.info(
                "Message processed successfully",
                extra={
                    'user_id': user_id,
                    'character_id': character_id,
                    'message_length': len(message),
                    'response_length': len(bot_response),
                    'duration_ms': duration * 1000,
                    'max_context_messages': max_context_messages
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
