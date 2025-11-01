from domain.entity.profile import UserProfile
from domain.service.profile_service import ProfileService
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageProfileUseCase:
    def __init__(self, profile_repository: ProfileRepository):
        self.profile_repo = profile_repository
        self.profile_service = ProfileService()
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
    def extract_and_update_profile(self, user_id: int, message: str) -> tuple:
        name, age, interests, mood = self.profile_service.extract_profile_info(message)

        profile = self.profile_repo.get_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)

        profile.update_profile(name, age, interests, mood)
        self.profile_repo.save_profile(profile)

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