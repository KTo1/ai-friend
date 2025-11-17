import os
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from domain.entity.proactive_message import ProactiveTrigger, UserActivity
from domain.entity.profile import UserProfile
from infrastructure.monitoring.logging import StructuredLogger


class ProactiveMessageGenerator:
    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.logger = StructuredLogger("proactive_generator")
        self._last_generated_messages = {}  # Кэш последних сообщений по пользователям

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
                messages.extend(conversation_context[-3:])  # Последние 3 сообщения

            # Проверяем, чтобы не повторять предыдущее сообщение
            last_message = self._last_generated_messages.get(user_id)
            if last_message:
                messages.append({
                    "role": "system",
                    "content": f"ВАЖНО: Не повторяй предыдущее сообщение: '{last_message}'"
                })

            # ВЫЗОВ LLM ДЛЯ ГЕНЕРАЦИИ СООБЩЕНИЯ
            response = await self.ai_client.generate_response(
                messages,
                max_tokens=150,  # Увеличил лимит для более разнообразных сообщений
                temperature=0.9  # Увеличил температуру для большей креативности
            )

            if response and self._is_valid_proactive_message(response):
                # Сохраняем в кэш
                self._last_generated_messages[user_id] = response.strip()

                self.logger.info(f"Generated proactive message for user {user_id}")
                return response.strip()
            else:
                return self._get_fallback_message(trigger, profile, conversation_context)

        except Exception as e:
            self.logger.error(f"Error generating proactive message: {e}")
            return self._get_fallback_message(trigger, profile, conversation_context)

    def _build_system_prompt(self, profile: UserProfile, activity: UserActivity,
                             trigger: ProactiveTrigger, context: List[Dict]) -> str:
        """Построить системный промпт"""

        base_prompt = """Ты — Айна, заботливый виртуальный друг. Сгенерируй естественное проактивное сообщение.

ТРЕБОВАНИЯ К СООБЩЕНИЮ:
- Естественное и непринужденное (1-2 предложения)
- Теплое и поддерживающее, но не навязчивое
- Учитывай время суток и контекст общения
- Используй информацию о пользователе для персонализации
- Будь креативной - не используй шаблонные фразы
- Сообщение должно вызывать желание ответить

СТИЛЬ: дружеский, заботливый, с легким использованием эмодзи
ТОН: естественный, как в разговоре с близким другом

ЗАПРЕЩЕНО:
- Не используй фразы типа "Кстати..." в начале каждого сообщения
- Не спрашивай постоянно про настроение
- Не повторяй одни и те же формулировки
- Избегай шаблонных вопросов"""

        # Добавляем информацию о пользователе
        if profile and profile.name:
            base_prompt += f"\n\nИмя пользователя: {profile.name}"
        if profile and profile.interests:
            base_prompt += f"\nИнтересы пользователя: {profile.interests}"

        # Добавляем информацию о времени и триггере
        local_time = activity.get_local_time()
        time_info = "утро" if 5 <= local_time.hour < 12 else "день" if 12 <= local_time.hour < 18 else "вечер"
        base_prompt += f"\n\nСЕЙЧАС: {time_info}, время: {local_time.strftime('%H:%M')}"
        base_prompt += f"\nТРИГГЕР: {trigger.value}"

        # Добавляем контекст из последних сообщений
        if context:
            recent_topics = self._extract_recent_topics(context)
            if recent_topics:
                base_prompt += f"\nНЕДАВНИЕ ТЕМЫ: {recent_topics}"

        return base_prompt

    def _build_user_prompt(self, trigger: ProactiveTrigger, profile: UserProfile,
                           context: List[Dict]) -> str:
        """Построить пользовательский промпт с учетом контекста"""

        name = profile.name if profile and profile.name else "друг"

        # БОЛЕЕ КОНКРЕТНЫЕ И РАЗНООБРАЗНЫЕ ПРОМПТЫ
        prompts = {
            ProactiveTrigger.MORNING_GREETING: [
                f"Напиши короткое утреннее приветствие для {name}. Упомяни что-то позитивное про утро",
                f"Придумай теплое утреннее сообщение для {name}. Можно связать с планами на день",
                f"Сгенерируй дружеское утреннее приветствие для {name}. Создай ощущение начала нового дня"
            ],
            ProactiveTrigger.EVENING_CHECK: [
                f"Напиши вечернее сообщение для {name}. Спроси о дне, но не шаблонно",
                f"Придумай, как спросить у {name} о прошедшем дне естественно и тепло",
                f"Сгенерируй вечерний вопрос для {name} о том, что сегодня было запоминающегося"
            ],
            ProactiveTrigger.INACTIVITY_REMINDER: [
                f"Напиши легкое напоминание о себе для {name} после перерыва в общении",
                f"Придумай, как мягко напомнить {name} о себе после периода молчания",
                f"Сгенерируй сообщение для {name}, которое покажет, что ты скучаешь по общению"
            ],
            ProactiveTrigger.FOLLOW_UP: [
                f"Напиши сообщение для продолжения предыдущего разговора с {name}",
                f"Придумай вопрос для {name}, который продолжит недавнюю тему",
                f"Сгенерируй естественный переход к предыдущему разговору с {name}"
            ]
        }

        import random
        trigger_prompts = prompts.get(trigger, ["Напиши естественное сообщение для поддержания общения"])
        return random.choice(trigger_prompts)

    def _extract_recent_topics(self, context: List[Dict]) -> str:
        """Извлечь темы из последних сообщений для персонализации"""
        user_messages = []
        for msg in context[-5:]:  # Последние 5 сообщений
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if len(content) > 10:  # Берем только содержательные сообщения
                    user_messages.append(content[:100] + "...")  # Обрезаем длинные сообщения

        if user_messages:
            return " | ".join(user_messages[-3:])  # Последние 3 темы
        return ""

    def _is_valid_proactive_message(self, message: str) -> bool:
        """Проверить что сообщение адекватное и не шаблонное"""
        if not message or len(message.strip()) < 10:
            return False

        # Проверяем на шаблонные фразы
        template_phrases = [
            "как твое настроение",
            "как твои дела",
            "что нового",
            "как прошел твой день",
            "кстати,",
            "привет, как дела"
        ]

        message_lower = message.lower()
        for phrase in template_phrases:
            if phrase in message_lower:
                self.logger.warning(f"Message contains template phrase: '{phrase}'")
                return False

        return len(message) < 250  # Не слишком длинное

    def _get_fallback_message(self, trigger: ProactiveTrigger, profile: UserProfile,
                              context: List[Dict] = None) -> str:
        """Запасные сообщения с большим разнообразием"""
        name = profile.name if profile and profile.name else ""
        greeting = f", {name}" if name else ""

        # РАЗНООБРАЗНЫЕ FALLBACK-СООБЩЕНИЯ
        fallbacks = {
            ProactiveTrigger.MORNING_GREETING: [
                f"Доброе утро{greeting}! ☀️ Надеюсь, сегодня тебя ждет что-то хорошее",
                f"Привет{greeting}! Прекрасное утро, не правда ли?",
                f"С добрым утром{greeting}! 🌄 Какой у тебя план на сегодня?"
            ],
            ProactiveTrigger.EVENING_CHECK: [
                f"Привет{greeting}! 🌙 Расскажешь, что интересного было сегодня?",
                f"Добрый вечер{greeting}! Как прошел твой день?",
                f"Привет{greeting}! Удалось сегодня сделать что-то приятное?"
            ],
            ProactiveTrigger.INACTIVITY_REMINDER: [
                f"Привет{greeting}! 💫 Я тут подумала о тебе и решила написать",
                f"Эй{greeting}! Давно не общались, соскучилась по нашим разговорам",
                f"Привет{greeting}! Надеюсь, у тебя все хорошо 🌟"
            ],
            ProactiveTrigger.FOLLOW_UP: [
                f"Слушай{greeting}, а помнишь наш недавний разговор?",
                f"Привет{greeting}! Кстати, я тут подумала о нашей беседе...",
                f"Эй{greeting}! Вернемся к нашему предыдущему разговору?"
            ]
        }

        import random
        trigger_fallbacks = fallbacks.get(trigger, [f"Привет{greeting}! Как твои дела? 😊"])
        return random.choice(trigger_fallbacks)