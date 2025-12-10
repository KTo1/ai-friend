from typing import Tuple, Dict, Optional
from datetime import datetime, timedelta
from domain.entity.tariff_plan import TariffPlan
from domain.entity.user_stats import UserStats
from infrastructure.database.repositories.rate_limit_tracking_repository import RateLimitTrackingRepository
from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
from infrastructure.monitoring.logging import StructuredLogger


class LimitService:
    """Сервис для проверки лимитов на основе тарифов"""

    def __init__(self,
                 rate_limit_tracking_repo: RateLimitTrackingRepository,
                 user_stats_repo: UserStatsRepository):
        self.rate_limit_tracking_repo = rate_limit_tracking_repo
        self.user_stats_repo = user_stats_repo
        self.logger = StructuredLogger("limit_service")

    def check_message_length(self, user_id: int, message: str, tariff: TariffPlan) -> Tuple[bool, Optional[str]]:
        """Проверить длину сообщения"""
        max_length = tariff.message_limits.max_message_length

        if len(message) > max_length:
            # Обновляем статистику
            stats = self.user_stats_repo.get_user_stats(user_id)
            if not stats:
                stats = UserStats(user_id=user_id)
            stats.record_message(len(message), was_rejected=True)
            self.user_stats_repo.save_user_stats(stats)

            error_msg = (
                f"🚫 Ваше сообщение слишком длинное ({len(message)} символов).\n"
                f"Максимально допустимая длина: {max_length} символов.\n\n"
                f"Пожалуйста, разделите ваше сообщение на несколько частей или сократите его."
            )

            self.logger.info(
                f"Message rejected - too long from user {user_id}",
                extra={
                    'user_id': user_id,
                    'message_length': len(message),
                    'limit': max_length
                }
            )

            return False, error_msg

        return True, None

    def check_rate_limit(self, user_id: int, tariff: TariffPlan) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Проверить rate limit"""
        # Сбрасываем счетчики если нужно
        self.rate_limit_tracking_repo.reset_counters_if_needed(user_id)

        # Получаем текущие счетчики
        counters = self.rate_limit_tracking_repo.get_counters(user_id)

        # Проверяем лимиты
        minute_limit_exceeded = counters['minute_counter'] >= tariff.rate_limits.messages_per_minute
        hour_limit_exceeded = counters['hour_counter'] >= tariff.rate_limits.messages_per_hour
        day_limit_exceeded = counters['day_counter'] >= tariff.rate_limits.messages_per_day

        if minute_limit_exceeded or hour_limit_exceeded or day_limit_exceeded:
            # Обновляем статистику
            stats = self.user_stats_repo.get_user_stats(user_id)
            if not stats:
                stats = UserStats(user_id=user_id)
            stats.record_message(0, was_rejected=False, was_rate_limited=True)
            self.user_stats_repo.save_user_stats(stats)

            # Формируем информацию о лимитах для сообщения об ошибке
            limits_info = self._get_limits_info(counters, tariff)
            error_message = self._format_rate_limit_message(limits_info)

            self.logger.warning(
                f"Rate limit exceeded for user {user_id}",
                extra={
                    'user_id': user_id,
                    'counters': counters,
                    'tariff_limits': {
                        'minute': tariff.rate_limits.messages_per_minute,
                        'hour': tariff.rate_limits.messages_per_hour,
                        'day': tariff.rate_limits.messages_per_day
                    }
                }
            )

            return False, error_message, limits_info

        return True, None, None

    def record_message_usage(self, user_id: int, message_length: int, tariff: TariffPlan):
        """Записать использование сообщения"""
        # Увеличиваем счетчики rate limit
        self.rate_limit_tracking_repo.increment_counters(user_id)

        # Обновляем статистику
        stats = self.user_stats_repo.get_user_stats(user_id)
        if not stats:
            stats = UserStats(user_id=user_id)
        stats.record_message(message_length, was_rejected=False, was_rate_limited=False)
        self.user_stats_repo.save_user_stats(stats)

    def get_user_limits_info(self, user_id: int, tariff: TariffPlan) -> Dict:
        """Получить информацию о лимитах пользователя"""
        counters = self.rate_limit_tracking_repo.get_counters(user_id)
        return self._get_limits_info(counters, tariff)

    def _get_limits_info(self, counters: Dict, tariff: TariffPlan) -> Dict:
        """Сформировать информацию о лимитах"""
        return {
            'current': {
                'minute': counters['minute_counter'],
                'hour': counters['hour_counter'],
                'day': counters['day_counter']
            },
            'limits': {
                'minute': tariff.rate_limits.messages_per_minute,
                'hour': tariff.rate_limits.messages_per_hour,
                'day': tariff.rate_limits.messages_per_day
            },
            'remaining': {
                'minute': max(0, tariff.rate_limits.messages_per_minute - counters['minute_counter']),
                'hour': max(0, tariff.rate_limits.messages_per_hour - counters['hour_counter']),
                'day': max(0, tariff.rate_limits.messages_per_day - counters['day_counter'])
            },
            'time_until_reset': {
                'minute': self._format_timedelta(
                    (counters['last_minute_reset'] + timedelta(minutes=1)) - datetime.utcnow()
                ),
                'hour': self._format_timedelta(
                    (counters['last_hour_reset'] + timedelta(hours=1)) - datetime.utcnow()
                ),
                'day': self._format_timedelta(
                    (counters['last_day_reset'] + timedelta(days=1)) - datetime.utcnow()
                )
            }
        }

    def _format_rate_limit_message(self, limits_info: Dict) -> str:
        """Форматировать сообщение о превышении лимита"""
        remaining = limits_info['remaining']
        time_until_reset = limits_info['time_until_reset']
        config = limits_info['limits']

        message = "⏰ Превышен лимит сообщений!\n\n"

        # Определяем какой именно лимит превышен
        if remaining['minute'] <= 0:
            message += f"• Минутный лимит: {config['minute']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['minute']}\n\n"
        elif remaining['hour'] <= 0:
            message += f"• Часовой лимит: {config['hour']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['hour']}\n\n"
        elif remaining['day'] <= 0:
            message += f"• Дневной лимит: {config['day']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['day']}\n\n"

        message += f"Осталось сообщений:\n"
        message += f"• В минуту: {remaining['minute']}/{config['minute']}\n"
        message += f"• В час: {remaining['hour']}/{config['hour']}\n"
        message += f"• В день: {remaining['day']}/{config['day']}\n\n"
        message += "Лимиты сбрасываются автоматически 🕒"

        return message

    def _format_timedelta(self, td: timedelta) -> str:
        """Форматировать timedelta в читаемую строку"""
        if td.total_seconds() <= 0:
            return "сейчас"

        total_seconds = int(td.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds} сек"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if seconds > 0:
                return f"{minutes} мин {seconds} сек"
            else:
                return f"{minutes} мин"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if minutes > 0:
                return f"{hours} ч {minutes} мин"
            else:
                return f"{hours} ч"