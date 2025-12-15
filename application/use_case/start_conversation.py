from domain.entity.profile import UserProfile
from domain.entity.user import User
from domain.service.tariff_service import TariffService
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class StartConversationUseCase:
    def __init__(self, user_repository: UserRepository, profile_repository: ProfileRepository, tariff_service: TariffService):
        self.user_repo = user_repository
        self.profile_repo = profile_repository
        self.tariff_service = tariff_service
        self.logger = StructuredLogger("start_conversation_uc")

    @trace_span("usecase.start_conversation", attributes={"component": "application"})
    def execute(self, user_id: int, username: str, first_name: str, last_name: str) -> str:
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        self.user_repo.save_user(user)

        # НАЗНАЧЕНИЕ ТАРИФА ПО УМОЛЧАНИЮ ПРИ ПЕРВОМ СТАРТЕ
        try:
            user_tariff = self.tariff_service.get_user_tariff(user.user_id)
            if not user_tariff:
                default_tariff = self.tariff_service.get_default_tariff()
                if default_tariff:
                    success, message = self.tariff_service.assign_tariff_to_user(user.user_id, default_tariff.id)
                    if success:
                        self.logger.info(f"Assigned default tariff '{default_tariff.name}' to new user {user.user_id}")

        except Exception as e:
            self.logger.error(f"Error assigning tariff to new user {user.user_id}: {e}")

        # СОЗДАЕМ ПУСТОЙ ПРОФИЛЬ, ЕСЛИ ЕГО НЕТ
        profile = self.profile_repo.get_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)
            self.profile_repo.save_profile(profile)
            self.logger.info(f"Created empty profile for new user {user_id}")

        if profile and profile.name:
            return f"🤗 Привет, {profile.name}! Рада снова тебя видеть!\n\nПомню, ты интересовался: {profile.interests or 'разными вещами'}\nКак у тебя дела сегодня? Что нового?"
        else:
            return "🤗 Привет! Я твой виртуальный друг Айна.\n\nЯ здесь, чтобы выслушать тебя, поддержать и просто пообщаться, когда тебе одиноко.\n\nКак мне тебя называть? И расскажи, что тебе интересно в жизни?"