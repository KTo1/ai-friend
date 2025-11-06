from domain.entity.user import User
from infrastructure.database.repositories.user_limits_repository import UserLimitsRepository
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class StartConversationUseCase:
    def __init__(self, user_repository: UserRepository, profile_repository: ProfileRepository, user_limits_repository: UserLimitsRepository):
        self.user_repo = user_repository
        self.profile_repo = profile_repository
        self.user_limits_repo = user_limits_repository
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
        self.user_limits_repo.set_user_limits(user.user_id, user.limits)

        profile = self.profile_repo.get_profile(user_id)

        if profile and profile.name:
            return f"🤗 Привет, {profile.name}! Рада снова тебя видеть!\n\nПомню, ты интересовался: {profile.interests or 'разными вещами'}\nКак у тебя дела сегодня? Что нового?"
        else:
            return "🤗 Привет! Я твой виртуальный друг Айна.\n\nЯ здесь, чтобы выслушать тебя, поддержать и просто пообщаться, когда тебе одиноко.\n\nКак мне тебя называть? И расскажи, что тебе интересно в жизни?"