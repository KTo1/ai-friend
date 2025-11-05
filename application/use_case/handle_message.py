import asyncio
import time

from typing import Dict, Any, List
from config.settings import Config
from domain.entity.user import UserLimits
from domain.service.context_service import ContextService
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.database.repositories.user_limits_repository import UserLimitsRepository
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


# application/use_case/handle_message.py
class HandleMessageUseCase:
    def __init__(self,
                 conversation_repository: ConversationRepository,
                 ai_client: AIClientInterface,
                 user_repository: UserRepository,
                 user_limits_repository: UserLimitsRepository):

        self.conversation_repo = conversation_repository
        self.ai_client = ai_client
        self.user_repo = user_repository
        self.user_limits_repo = user_limits_repository
        self.context_service = ContextService()
        self.logger = StructuredLogger("handle_message_uc")
        self.config = Config()

    async def execute(self, user_id: int, message: str, system_prompt: str, profile_data: dict = None) -> str:
        """Обработать сообщение пользователя с полной проверкой лимитов и метриками"""
        try:
            # 📊 МЕТРИКА: сообщение получено
            metrics_collector.record_message_received("text")
            start_time = time.time()

            # 🛡️ 0. ПРОВЕРКА RATE LIMITS
            rate_limit_check = self.user_limits_repo.check_rate_limits(user_id)
            if not rate_limit_check["allowed"]:
                metrics_collector.record_request_blocked("rate_limit")
                self.logger.warning(
                    "Rate limit exceeded",
                    extra={
                        'user_id': user_id,
                        'minute_count': rate_limit_check["minute_count"],
                        'hour_count': rate_limit_check["hour_count"],
                        'block_type': 'rate_limit'
                    }
                )
                return f"Слишком частые сообщения! Лимиты: {rate_limit_check['minute_remaining']}/мин, {rate_limit_check['hour_remaining']}/час"

            # 🛡️ 1. ПРОВЕРКА СТАТУСА ПОЛЬЗОВАТЕЛЯ
            user_validation = await self.validate_user_access(user_id)
            if not user_validation["allowed"]:
                # 📊 МЕТРИКА: запрос заблокирован (пользователь)
                metrics_collector.record_request_blocked("user_status")
                self.logger.warning(
                    "User access denied",
                    extra={
                        'user_id': user_id,
                        'reason': user_validation.get('reason', 'unknown'),
                        'block_type': 'user_status'
                    }
                )
                return user_validation["error_message"]

            # 🛡️ 2. ВАЛИДАЦИЯ СООБЩЕНИЯ
            message_validation = self.validate_message(user_id, message)
            if not message_validation["is_valid"]:
                # 📊 МЕТРИКА: запрос заблокирован (сообщение)
                metrics_collector.record_request_blocked("message_validation")
                self.logger.warning(
                    "Message validation failed",
                    extra={
                        'user_id': user_id,
                        'violations': message_validation.get('violations', []),
                        'block_type': 'message_validation'
                    }
                )
                return message_validation["error_message"]

            truncated_message = message_validation["truncated_message"]

            # 🛡️ 3. ПРОВЕРКА ТЕХНИЧЕСКИХ ЗАПРОСОВ
            if self.is_technical_request(truncated_message):
                # 📊 МЕТРИКА: технический запрос заблокирован
                metrics_collector.record_technical_block("pre_ai")
                metrics_collector.record_request_blocked("technical")
                self.logger.warning(
                    "Technical request blocked",
                    extra={'user_id': user_id, 'block_type': 'technical'}
                )
                return self.get_blocked_response()

            # 🛡️ 4. ОГРАНИЧЕНИЕ КОНТЕКСТА
            user_limits = self.user_limits_repo.get_user_limits(user_id) or UserLimits()
            context_messages = self.conversation_repo.get_conversation_context(
                user_id,
                limit=user_limits.max_context_messages
            )

            # 📊 МЕТРИКА: длина контекста
            metrics_collector.record_conversation_length(len(context_messages))

            # 🛡️ 5. ПОДГОТОВКА С ПРОВЕРКОЙ ТОКЕНОВ
            messages = self.context_service.prepare_messages_for_ai(
                system_prompt, context_messages, truncated_message
            )

            messages_for_token_count = context_messages + [{"role": "user", "content": truncated_message}]
            estimated_tokens = self.estimate_tokens(messages_for_token_count)

            # 📊 МЕТРИКА: оценка токенов
            metrics_collector.record_tokens_estimated(estimated_tokens)

            if estimated_tokens > user_limits.max_tokens_per_request:
                # 📊 МЕТРИКА: превышение лимита токенов
                metrics_collector.record_request_blocked("token_limit")
                metrics_collector.record_token_limit_exceeded(estimated_tokens, user_limits.max_tokens_per_request)
                self.logger.warning(
                    "Token limit exceeded",
                    extra={
                        'user_id': user_id,
                        'estimated_tokens': estimated_tokens,
                        'user_limit': user_limits.max_tokens_per_request,
                        'block_type': 'token_limit'
                    }
                )
                return f"Сообщение слишком объемное (оценка: {estimated_tokens} токенов). Максимум: {user_limits.max_tokens_per_request} токенов."

            # 🛡️ 6. ВЫПОЛНЕНИЕ ЗАПРОСА К AI
            response = await self.ai_client.generate_response_safe(
                messages,
                max_tokens=min(500, user_limits.max_tokens_per_request)
            )

            # 🛡️ 7. ОБНОВЛЕНИЕ СТАТИСТИКИ
            actual_tokens = self.estimate_tokens([{"content": response}]) + estimated_tokens
            estimated_cost = self.estimate_cost(actual_tokens)

            self.user_limits_repo.increment_user_usage(
                user_id, actual_tokens, estimated_cost
            )

            # 📊 МЕТРИКА: успешная обработка
            duration = time.time() - start_time
            metrics_collector.record_processing_time("message_processing", duration)
            metrics_collector.record_message_processed("success")
            metrics_collector.record_tokens_used(actual_tokens)
            metrics_collector.record_api_cost(self.ai_client.provider_name, estimated_cost)

            # 📊 МЕТРИКА: использование пользователя
            usage_today = self.user_limits_repo.get_user_usage_today(user_id)
            metrics_collector.record_user_usage(user_id, usage_today['requests_count'])

            self.logger.info(
                "Message processed successfully",
                extra={
                    'user_id': user_id,
                    'message_length': len(truncated_message),
                    'response_length': len(response),
                    'estimated_tokens': estimated_tokens,
                    'actual_tokens': actual_tokens,
                    'estimated_cost': estimated_cost,
                    'duration_ms': duration * 1000,
                    'user_requests_today': usage_today['requests_count']
                }
            )

            # Сохраняем ответ
            self.conversation_repo.save_message(user_id, "assistant", response)

            return response

        except Exception as e:
            # 📊 МЕТРИКА: ошибка обработки
            metrics_collector.record_message_processed("error")
            self.logger.error(
                f"Error processing message: {e}",
                extra={'user_id': user_id, 'operation': 'handle_message'}
            )
            return "Произошла ошибка при обработке сообщения."

    def validate_message(self, user_id: int, message: str) -> Dict[str, any]:
        """Валидация сообщения пользователя"""
        violations = []

        # Проверка длины сообщения
        user_limits = self.user_limits_repo.get_user_limits(user_id) or UserLimits()
        if len(message) > user_limits.max_message_length:
            violations.append(f"message_too_long:{len(message)}>{user_limits.max_message_length}")
            return {
                "is_valid": False,
                "error_message": f"Сообщение слишком длинное. Максимум: {user_limits.max_message_length} символов.",
                "violations": violations,
                "truncated_message": message[:user_limits.max_message_length]
            }

        # Проверка на пустое сообщение
        if not message.strip():
            violations.append("empty_message")
            return {
                "is_valid": False,
                "error_message": "Сообщение не может быть пустым.",
                "violations": violations,
                "truncated_message": ""
            }

        return {
            "is_valid": True,
            "error_message": None,
            "violations": violations,
            "truncated_message": message
        }

    def is_technical_request(self, message: str) -> bool:
        """Проверка на технический запрос"""
        technical_keywords = [
            'напиши код', 'программирование', 'скрипт', 'алгоритм',
            'функция', 'переменная', 'база данных', 'sql', 'api',
            'технический', 'debug', 'отладка', 'ошибка в коде'
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in technical_keywords)

    def get_blocked_response(self) -> str:
        """Сообщение для заблокированных технических запросов"""
        return "Извини, я не могу помочь с техническими вопросами. Я здесь чтобы быть твоим другом! 😊"

    def estimate_tokens(self, messages: List[Dict]) -> int:
        """Оценка количества токенов (упрощенная)"""
        # Примерная оценка: 1 токен ≈ 4 символа для английского, ≈ 2 символа для русского
        total_chars = sum(len(msg.get('content', '')) for msg in messages)
        return total_chars // 2  # Упрощенная оценка для русского текста

    def estimate_cost(self, tokens: int) -> float:
        """Оценка стоимости запроса"""
        # Примерная стоимость: $0.002 за 1K токенов для GPT-3.5
        return (tokens / 1000) * 0.002

    async def validate_user_access(self, user_id: int) -> Dict[str, any]:
        """Полная проверка доступа пользователя с метриками"""
        user = self.user_repo.get_user(user_id)
        if not user:
            # 📊 МЕТРИКА: пользователь не найден
            metrics_collector.record_user_not_found()
            return {
                "allowed": False,
                "error_message": "Пользователь не найден.",
                "reason": "user_not_found"
            }

        # Проверка бана
        if user.is_banned:
            # 📊 МЕТРИКА: пользователь забанен
            metrics_collector.record_banned_user_access_attempt()
            return {
                "allowed": False,
                "error_message": "🔒 Ваш аккаунт заблокирован.",
                "reason": "banned"
            }

        # Проверка активности
        if not user.is_active:
            # 📊 МЕТРИКА: пользователь деактивирован
            metrics_collector.record_inactive_user_access_attempt()
            return {
                "allowed": False,
                "error_message": "🔒 Аккаунт деактивирован.",
                "reason": "inactive"
            }

        # Проверка дневного лимита
        usage_today = self.user_limits_repo.get_user_usage_today(user_id)
        user_limits = self.user_limits_repo.get_user_limits(user_id) or UserLimits()

        if usage_today['requests_count'] >= user_limits.max_daily_requests:
            # 📊 МЕТРИКА: превышен дневной лимит
            metrics_collector.record_daily_limit_exceeded()
            remaining = user_limits.max_daily_requests - usage_today['requests_count']
            return {
                "allowed": False,
                "error_message": f"📊 Превышен дневной лимит запросов. Доступно: {user_limits.max_daily_requests}/день. Использовано: {usage_today['requests_count']}.",
                "reason": "daily_limit_exceeded"
            }

        return {"allowed": True, "error_message": None, "reason": "success"}