from domain.entity.character import Character
from domain.entity.profile import UserProfile
from domain.service.profile_service import ProfileService
from domain.interfaces.ai_client import AIClientInterface

from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger



class ManageProfileUseCase:
    def __init__(self, profile_repository: ProfileRepository,
                 ai_client: AIClientInterface):
        self.profile_repo = profile_repository
        self.profile_service = ProfileService(ai_client)
        self.logger = StructuredLogger("manage_profile_uc")

    @trace_span("usecase.extract_profile", attributes={"component": "application"})
    async def extract_and_update_profile(self, user_id: int, message: str, character: Character) -> str:

        # 5. Вызываем новый async метод LLM
        name, age, interests, mood, gender = await self.profile_service.extract_profile_info_llm(message, character)

        # Если LLM ничего не вернул (не было триггеров или данных), выходим
        if not any([name, age, interests, mood, gender]):
            return str(UserProfile(user_id))

        # 6. Обновляем профиль в базе
        profile = self.profile_repo.get_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)

        # Сервис `update_profile` в entity обновляет только то, что не None
        profile.update_profile(name, age, interests, mood, gender)
        self.profile_repo.save_profile(profile)

        self.logger.info(
            f"Profile updated for user {user_id}",
            extra={'user_id': user_id, 'extracted_name': name, 'extracted_age': age, 'extracted_interests': interests, 'extracted_mood': mood, 'extracted_gender': gender}
        )

        return str(profile)
