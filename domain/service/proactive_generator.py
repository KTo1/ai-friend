# domain/service/proactive_generator.py
import os
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from domain.entity.proactive_message import ProactiveTrigger, UserActivity
from domain.entity.profile import UserProfile
from infrastructure.monitoring.logging import StructuredLogger


class ProactiveMessageGenerator:
    """
    Генератор проактивных сообщений.
    Улучшения:
    - Убраны все вложенные таймауты
    - Простая логика с ретраями
    - Безопасная генерация без сложных конструкций
    """

    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.logger = StructuredLogger("proactive_generator")
        # Кэш последних сообщений по пользователям (список последних N)
        self._last_generated_messages: Dict[int, List[str]] = {}
        self._KEEP_LAST = 3  # Уменьшили для экономии памяти

    def get_last_for_user(self, user_id: int) -> Optional[str]:
        """Вернуть последний сгенерированный текст для пользователя (или None)"""
        lst = self._last_generated_messages.get(user_id)
        if lst:
            return lst[-1]
        return None

    async def generate_proactive_message(self,
                                         user_id: int,
                                         profile: UserProfile,
                                         activity: UserActivity,
                                         trigger: ProactiveTrigger,
                                         conversation_context: List[Dict]) -> Optional[str]:
        """Сгенерировать проактивное сообщение через LLM на основе контекста"""

        try:
            # Используем LLM для генерации контекстных сообщений
            system_prompt = self._build_system_prompt(profile, activity, trigger, conversation_context)
            user_prompt = self._build_user_prompt(trigger, profile, conversation_context)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Добавляем контекст разговора для персонализации
            if conversation_context:
                messages.extend(conversation_context[-2:])  # Последние 2 сообщения

            # ВЫЗОВ LLM ДЛЯ ГЕНЕРАЦИИ СООБЩЕНИЯ
            # Используем безопасный метод с ретраями
            response = await self._safe_generate_with_retry(messages)

            # Гарантируем что ответ существует
            if response and isinstance(response, str):
                candidate = response.strip()

                # Валидация: проверяем, что сообщение не шаблонное и достаточно содержательное
                if self._is_valid_proactive_message(candidate):
                    # Сохраняем в кэш последних сообщений
                    lst = self._last_generated_messages.setdefault(user_id, [])
                    lst.append(candidate)
                    if len(lst) > self._KEEP_LAST:
                        lst.pop(0)

                    self.logger.debug(f"Generated proactive message for user {user_id}")
                    return candidate
                else:
                    # Если LLM вернул шаблонную фразу — используем наш более разнообразный fallback
                    self.logger.debug("Generated message rejected by _is_valid_proactive_message, using fallback")
                    fallback = self._get_fallback_message(trigger, profile, conversation_context)
                    # Сохраняем fallback тоже в кэш
                    lst = self._last_generated_messages.setdefault(user_id, [])
                    lst.append(fallback)
                    if len(lst) > self._KEEP_LAST:
                        lst.pop(0)
                    return fallback
            else:
                # Если LLM не дал ответа — fallback
                self.logger.warning("LLM returned empty response, using fallback")
                fallback = self._get_fallback_message(trigger, profile, conversation_context)
                lst = self._last_generated_messages.setdefault(user_id, [])
                lst.append(fallback)
                if len(lst) > self._KEEP_LAST:
                    lst.pop(0)
                return fallback

        except Exception as e:
            self.logger.error(f"Error generating proactive message: {e}")
            # На ошибки — fallback
            fallback = self._get_fallback_message(trigger, profile, conversation_context)
            lst = self._last_generated_messages.setdefault(user_id, [])
            lst.append(fallback)
            if len(lst) > self._KEEP_LAST:
                lst.pop(0)
            return fallback

    async def _safe_generate_with_retry(self, messages: List[Dict]) -> str:
        """Безопасная генерация с ретраями"""
        max_retries = 2
        fallback_responses = [
            "Привет! Как твои дела? 😊",
            "Извини, я немного занята. Расскажи, что у тебя нового? 🌟",
            "Привет! Что интересного произошло? 🎯",
            "Здравствуй! Как твое настроение сегодня? 💫"
        ]

        import random

        for attempt in range(max_retries):
            try:
                # Простой вызов без вложенных таймаутов
                response = await self.ai_client.generate_response(
                    messages,
                    max_tokens=150,  # Уменьшили для проактивных сообщений
                    temperature=0.8
                )
                return response

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    self.logger.error(f"All attempts failed, using fallback: {e}")
                    return random.choice(fallback_responses)

        return random.choice(fallback_responses)

    def _build_system_prompt(self, profile: UserProfile, activity: UserActivity,
                             trigger: ProactiveTrigger, context: List[Dict]) -> str:
        """Построить системный промпт"""
        base_prompt = """Ты — Айна, заботливый виртуальный друг. Сгенерируй естественное проактивное сообщение.

ТРЕБОВАНИЯ К СООБЩЕНИЮ:
- Естественное и непринужденное (1-2 предложения, 50 - 150 символов)
- Теплое и поддерживающее, но не навязчивое
- Учитывай время суток и контекст общения
- Используй информацию о пользователе для персонализации

СТИЛЬ: дружеский, заботливый, с лёгким использованием эмодзи
ТОН: естественный, как в разговоре с близким другом

ЗАПРЕЩЕНО:
- Не используй фразы типа "Кстати..." в начале каждого сообщения
- Не спрашивай постоянно про настроение
- Не повторяй одни и те же формулировки
- Избегай шаблонных вопросов"""

        return base_prompt

    def _build_user_prompt(self, trigger: ProactiveTrigger, profile: UserProfile, context: List[Dict]) -> str:
        """Построить пользовательскую подсказку (кратко)"""
        name = profile.name if profile and profile.name else ""
        recent_topics = self._extract_recent_topics(context)
        if recent_topics:
            recent_part = f" Упомяни недавние темы: {recent_topics}."
        else:
            recent_part = ""

        trigger_label = trigger.name.replace("_", " ").lower()
        return f"Задача: создай дружеское, ненавязчивое сообщение для {name}. Контекст триггера: {trigger_label}.{recent_part}"

    def _extract_recent_topics(self, context: List[Dict]) -> str:
        """Извлечь темы из последних сообщений для персонализации"""
        user_messages = []
        for msg in (context or [])[-3:]:  # Последние 3 сообщения
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if len(content) > 10:
                    user_messages.append(content[:100])  # Укоротили
        if user_messages:
            return " | ".join(user_messages[-2:])  # Только 2 последние
        return ""

    def _is_valid_proactive_message(self, message: str) -> bool:
        """Проверить что сообщение адекватное и не шаблонное"""
        if not message or len(message.strip()) < 5:
            return False

        # Проверяем на шаблонные фразы
        template_phrases = [
            "как твое настроение",
            "как твои дела",
            "что нового",
            "как прошел твой день",
            "кстати,",
            "привет, как дела",
            "как настроение",
            "как дела"
        ]

        message_lower = message.lower()
        for phrase in template_phrases:
            if phrase in message_lower:
                self.logger.debug(f"Message contains template phrase: '{phrase}'")
                return False

        # Ограничение длины
        return 5 <= len(message) <= 200

    def _get_fallback_message(self, trigger: ProactiveTrigger, profile: UserProfile,
                              context: List[Dict] = None) -> str:
        """Запасные сообщения с большим разнообразием"""
        name = profile.name if profile and profile.name else ""
        greeting = f", {name}" if name else ""

        import random

        # Простые fallback сообщения без сложной логики
        fallbacks = {
            ProactiveTrigger.MORNING_GREETING: [
                f"Доброе утро{greeting}! ☀️",
                f"Хорошего утра{greeting}! 😊",
                f"С добрым утром{greeting}! 🌄"
            ],
            ProactiveTrigger.EVENING_CHECK: [
                f"Добрый вечер{greeting}.",
                f"Вечерний привет{greeting}!",
                f"Привет{greeting}, как день?"
            ],
            ProactiveTrigger.INACTIVITY_REMINDER: [
                f"Привет{greeting}! Как ты?",
                f"Эй{greeting}! Скучаю по нашим разговором.",
                f"Привет{greeting}! Я рядом."
            ],
            ProactiveTrigger.FOLLOW_UP: [
                f"Слушай{greeting}, как там дела?",
                f"Эй{greeting}! Есть вопрос по нашей беседе.",
                f"Привет{greeting}! Хотела спросить..."
            ]
        }

        trigger_fallbacks = fallbacks.get(trigger, [f"Привет{greeting}! Я рядом, если хочешь поговорить."])
        return random.choice(trigger_fallbacks)