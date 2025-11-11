from domain.entity.profile import UserProfile
from domain.service.profile_service import ProfileService
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from domain.interfaces.ai_client import AIClientInterface  # <--- 1. Импортируем AIClient
from typing import Tuple


class ManageProfileUseCase:
    def __init__(self, profile_repository: ProfileRepository,
                 ai_client: AIClientInterface):
        self.profile_repo = profile_repository
        self.profile_service = ProfileService(ai_client)
        self.logger = StructuredLogger("manage_profile_uc")

    @trace_span("usecase.get_profile", attributes={"component": "application"})
    def get_profile(self, user_id: int) -> str:
        profile = self.profile_repo.get_profile(user_id)

        if profile:
            return f"""
📋 Твой профиль:

👤 Имя: {profile.name or 'не указано'}
🎂 Возраст: {profile.age or 'не указан'}
🎯 Интересы: {profile.interests or 'не указаны'}
😊 Последнее настроение: {profile.mood or 'не указано'}

Хочешь что-то изменить? Просто напиши:
"Меня зовут ..." или "Мои интересы ..."
            """
        else:
            return "У тебя еще нет профиля. Давай создадим его! Как тебя зовут?"

    @trace_span("usecase.extract_profile", attributes={"component": "application"})
    async def extract_and_update_profile(self, user_id: int, message: str) -> tuple:

        # 5. Вызываем новый async метод LLM
        name, age, interests, mood = await self.profile_service.extract_profile_info_llm(message)

        # Если LLM ничего не вернул (не было триггеров или данных), выходим
        if not any([name, age, interests, mood]):
            return None, None, None, None

        # 6. Обновляем профиль в базе
        profile = self.profile_repo.get_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)

        # Сервис `update_profile` в entity обновляет только то, что не None
        profile.update_profile(name, age, interests, mood)
        self.profile_repo.save_profile(profile)

        self.logger.info(
            f"Profile updated for user {user_id}",
            extra={'user_id': user_id, 'extracted_name': name, 'extracted_age': age, 'extracted_interests': interests, 'extracted_mood': mood}
        )
        return name, age, interests, mood

    @trace_span("usecase.get_memory", attributes={"component": "application"})
    def get_memory(self, user_id: int) -> str:
        profile = self.profile_repo.get_profile(user_id)

        if profile and (profile.name or profile.interests):
            memory_text = "Я помню о тебе:\n"

            if profile.name:
                memory_text += f"• Тебя зовут {profile.name}\n"
            if profile.age:
                memory_text += f"• Тебе {profile.age} лет\n"
            if profile.interests:
                memory_text += f"• Ты интересуешься: {profile.interests}\n"
            if profile.mood:
                memory_text += f"• Последний раз у тебя было настроение: {profile.mood}\n"
        else:
            memory_text = "Я еще мало что знаю о тебе. Расскажи о себе больше! 😊"

        return memory_text