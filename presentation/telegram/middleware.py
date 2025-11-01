from domain.entity.user import User


class TelegramMiddleware:
    @staticmethod
    def create_user_from_telegram(telegram_user) -> User:
        return User(
            user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )