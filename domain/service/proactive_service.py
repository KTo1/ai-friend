from domain.interfaces.ai_client import AIClientInterface
from domain.service.context_service import ContextService
from domain.service.tariff_service import TariffService

from infrastructure.database.repositories.character_repository import CharacterRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository


class ProactiveService:
    """Чистая бизнес-логика проактивных сообщений."""

    def __init__(self, ai_client: AIClientInterface, tariff_service: TariffService, conversation_repo: ConversationRepository, character_repo: CharacterRepository, profile_repo: ProfileRepository):
        self.ai_client = ai_client
        self.tariff_service = tariff_service
        self.conversation_repo = conversation_repo
        self.character_repo = character_repo
        self.profile_repo = profile_repo
        self.context_service = ContextService()

    async def generate_proactive_message(self, user_id: int, character_id: int) -> str:
        """Генерирует текст проактивного сообщения с контекстом."""

        # Получаем персонажа для его системного промпта
        character = self.character_repo.get_character(character_id)
        if not character:
            self.logger.error(f'Character {character_id} not found for user {user_id}')
            return ""

        profile = self.profile_repo.get_profile(user_id)
        profile_data = str(profile)

        user_tariff = self.tariff_service.get_user_tariff(user_id)

        context_messages = self.conversation_repo.get_conversation_context(
            user_id,
            character_id,
            max_context_messages=user_tariff.tariff_plan.message_limits.max_context_messages
        ) or []

        # Явный промпт для проактивного сообщения (как "user input")
        proactive_prompt = (
            "Пользователь не писал тебе уже 24 часа. Напомни о себе дружелюбно, "
            "заинтересуй продолжить разговор, но не будь навязчивой. "
            "Можешь спросить, как дела, или сослаться на предыдущую тему. "
            "Учти профиль пользователя и стиль персонажа."
        )

        # Подготавливаем сообщения для AI
        enhanced_system_prompt = (f"""СИСТЕМНЫЙ ПРОМТП, ПОВЕДЕНИЕ ПЕРСОНАЖА: {character.system_prompt}\n\n                                           
                                  ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ, ИСПОЛЬЗУЙ ЭТО В РАЗГОВОРЕ, ЕСЛИ КАКИХ-ТО ДАННЫХ НЕТ (NONE), ТО ОЧЕНЬ НЕНАВЯЗЧИВО СПРАШИВАЙ О НИХ:  {profile_data} \n\n
                                  ВАЖНО!!!!! ОБЯЗТЕЛЬНО УЧТИ, ЧТО ПОЛЬЗОВАТЕЛЬ НЕ ОТВЕЧАЛ СУТКИ (24 ЧАСА), И СОСТАВЬ СООБЩЕНИЕ С УЧЕТОМ ЭТОГО \n\n """)
        messages = self.context_service.prepare_messages_for_ai(
            enhanced_system_prompt, context_messages, proactive_prompt
        )

        # БЕЗОПАСНАЯ генерация ответа
        try:
            bot_response = await self.ai_client.generate_response_safe(messages)
        except Exception as e:
            self.logger.error(f"AI response error: {e}")
            bot_response = "Извини, что-то пошло не так... Попробуй написать еще раз! 🔄"

        return bot_response

