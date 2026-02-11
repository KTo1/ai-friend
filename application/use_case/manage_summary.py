from datetime import datetime
from domain.entity.conversation_summary import ConversationSummary
from domain.service.summary_service import SummaryService
from infrastructure.database.repositories.summary_repository import SummaryRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.monitoring.logging import StructuredLogger


class ManageSummaryUseCase:

    def __init__(self, summary_repository: SummaryRepository,
                 conversation_repository: ConversationRepository,
                 summary_service: SummaryService):
        self.summary_repo = summary_repository
        self.conversation_repo = conversation_repository
        self.summary_service = summary_service
        self.logger = StructuredLogger('manage_summary_uc')

    async def check_and_update_summaries(self, user_id: int, character_id: int,
                                         character_name: str) -> bool:
        """Проверяет и обновляет суммаризации при необходимости"""

        try:
            # сюда попадает каждое второео
            level_1_messages_count = 8

            # Получаем историю сообщений
            messages_count = self.conversation_repo.get_conversation_count(user_id, character_id)

            if messages_count == 0 or messages_count % level_1_messages_count != 0:
                return False

            messages = self.conversation_repo.get_conversation_context(
                user_id, character_id, max_context_messages=level_1_messages_count
            ) or []

            generated = False
            previous_summary_content = ""

            # Уровень 1: Краткая суммаризация диалога
            previous_summary = self.summary_repo.get_summary(user_id, character_id, level=1)
            if previous_summary:
                previous_summary_content = previous_summary.content

            summary_data = await self.summary_service.generate_dialog_summary(
                messages, previous_summary_content, character_name
            )

            if summary_data:
                summary = ConversationSummary(
                    user_id=user_id,
                    character_id=character_id,
                    level=1,
                    content=summary_data['content']
                )

                if self.summary_repo.save_summary(summary):
                    self.logger.info(
                        f'Generated level 1 summary for user {user_id}',
                        extra={'user_id': user_id, 'character_id': character_id}
                    )
                    generated = True

            # # Уровень 2: Детальная суммаризация сессии/отношений
            # level2_summary = self.summary_repo.get_summary(user_id, character_id, level=2)
            #
            # hours_since_last = 999  # Большое значение по умолчанию
            # if level2_summary:
            #     hours_since_last = (datetime.utcnow() - level2_summary.updated_at).total_seconds() / 3600
            #
            # if self.summary_service.should_generate_level2(len(messages), hours_since_last):
            #     # Получаем предыдущие суммаризации для контекста
            #     previous_summaries = []
            #     if level1_summary:
            #         previous_summaries.append(level1_summary.content)
            #
            #     summary_data = await self.summary_service.generate_session_summary(
            #         messages, previous_summaries, character_name
            #     )
            #
            #     if summary_data:
            #         summary = ConversationSummary(
            #             user_id=user_id,
            #             character_id=character_id,
            #             level=2,
            #             content=summary_data['content'],
            #             message_count=summary_data['message_count']
            #         )
            #
            #         if self.summary_repo.save_summary(summary):
            #             self.logger.info(
            #                 f'Generated level 2 summary for user {user_id}',
            #                 extra={'user_id': user_id, 'character_id': character_id}
            #             )
            #             generated = True

            return generated

        except Exception as e:
            self.logger.error(f'Error in check_and_update_summaries: {e}')
            return False

    def get_summary_context(self, user_id: int, character_id: int) -> str:
        """Получает суммаризации для контекста AI"""

        try:
            summaries = self.summary_repo.get_all_summaries(user_id, character_id)
            return self.summary_service.prepare_for_context(summaries)
        except Exception as e:
            self.logger.error(f'Error getting summary context: {e}')
            return ""

    def clear_summaries(self, user_id: int, character_id: int) -> bool:
        """Очищает все суммаризации пользователя"""

        try:
            success = self.summary_repo.delete_summaries(user_id, character_id)
            if success:
                self.logger.info(f'Cleared all summaries for user {user_id}, character {character_id}')
            return success
        except Exception as e:
            self.logger.error(f'Error clearing summaries: {e}')
            return False