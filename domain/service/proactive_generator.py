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
    - Метод get_last_for_user для проверки последнего сгенерированного сообщения (используется менеджером)
    - Улучшенная валидация и более разнообразный fallback через _get_fallback_message (без шаблонных фраз)
    - Хранение последних N сгенерированных сообщений в памяти для дедупа
    """

    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.logger = StructuredLogger("proactive_generator")
        # Кэш последних сообщений по пользователям (список последних N)
        self._last_generated_messages: Dict[int, List[str]] = {}
        self._KEEP_LAST = 5

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
                messages.extend(conversation_context[-3:])  # Последние 3 сообщения

            # Проверяем, чтобы не повторять предыдущее сообщение
            last_messages = self._last_generated_messages.get(user_id, [])
            if last_messages:
                # даём модели явное указание не повторять N последних сообщений
                not_repeat = "|".join([m.replace("\n", " ")[:200] for m in last_messages[-3:]])
                messages.append({
                    "role": "system",
                    "content": f"ВАЖНО: не используй и не повторяй фразы, похожие на: {not_repeat}"
                })

            # ВЫЗОВ LLM ДЛЯ ГЕНЕРАЦИИ СООБЩЕНИЯ
            response = await self.ai_client.generate_response_safe(
                messages,
                max_tokens=250,  # лимит для проактива
                temperature=0.9  # побольше креативности
            )

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

                    self.logger.info(f"Generated proactive message for user {user_id}")
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

    def _build_system_prompt(self, profile: UserProfile, activity: UserActivity,
                             trigger: ProactiveTrigger, context: List[Dict]) -> str:
        """Построить системный промпт"""
        base_prompt = """Ты — Айна, заботливый виртуальный друг. Сгенерируй естественное проактивное сообщение.

ТРЕБОВАНИЯ К СООБЩЕНИЮ:
- Естественное и непринужденное (1-2 предложения, 100 - 200 символов)
- Теплое и поддерживающее, но не навязчивое
- Учитывай время суток и контекст общения
- Используй информацию о пользователе для персонализации
- Не используй шаблонные фразы вроде: 'как твое настроение', 'что нового', 'кстати'
- Сообщение должно вызывать желание ответить

СТИЛЬ: дружеский, заботливый, с лёгким использованием эмодзи
ТОН: естественный, как в разговоре с близким другом

ЗАПРЕЩЕНО:
- Не используй фразы типа "Кстати..." в начале каждого сообщения
- Не спрашивай постоянно про настроение
- Не повторяй одни и те же формулировки
- Избегай шаблонных вопросов"""

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
        for msg in (context or [])[-5:]:  # Последние 5 сообщений
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if len(content) > 10:
                    user_messages.append(content[:120])
        if user_messages:
            return " | ".join(user_messages[-3:])
        return ""

    def _is_valid_proactive_message(self, message: str) -> bool:
        """Проверить что сообщение адекватное и не шаблонное"""
        if not message or len(message.strip()) < 10:
            return False

        # Проверяем на шаблонные фразы (расширенный список)
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
                self.logger.warning(f"Message contains template phrase: '{phrase}'")
                return False

        # Ограничение длины, но допускаем краткость
        return 10 <= len(message) <= 300

    def _get_fallback_message(self, trigger: ProactiveTrigger, profile: UserProfile,
                              context: List[Dict] = None) -> str:
        """Запасные сообщения с большим разнообразием (убраны самые шаблонные фразы)"""
        name = profile.name if profile and profile.name else ""
        greeting = f", {name}" if name else ""

        fallbacks = {
            ProactiveTrigger.MORNING_GREETING: [
                f"Доброе утро{greeting}! ☀️ Сегодня хочется верить, что день будет тёплым — как тебе такое начало?",
                f"Хорошего утра{greeting}! 😊 Есть что-то, что сегодня тебя радует?",
                f"С добрым утром{greeting}! 🌄 Маленькая мысль на день: что бы ты хотел сделать первым?"
            ],
            ProactiveTrigger.EVENING_CHECK: [
                f"Добрый вечер{greeting}. Какой момент дня сегодня особенно запомнился?",
                f"Я тут подумала о нашем разговоре — хочешь поделиться, как прошёл день?",
                f"Вечерний привет{greeting}! Было ли сегодня что-то приятное?"
            ],
            ProactiveTrigger.INACTIVITY_REMINDER: [
                f"Я просто решила написать и сказать, что думаю о тебе{greeting}. Как ты?",
                f"Эй{greeting}! Скучаю по нашим разговором — может, расскажешь что-то новое?",
                f"Привет{greeting}! Просто мягкое напоминание: я рядом, если хочешь поболтать."
            ],
            ProactiveTrigger.FOLLOW_UP: [
                f"Слушай{greeting}, а помнишь нашу последнюю тему? Хотела бы узнать, как там дела...",
                f"Я тут вспомнила, о чём мы говорили — хочется продолжить, если хочешь.",
                f"Эй{greeting}! Есть небольшой вопрос по нашей прошлой беседе — хочешь обсудить?"
            ]
        }

        import random
        trigger_fallbacks = fallbacks.get(trigger, [f"Привет{greeting}! Я рядом, если хочешь поговорить."])
        return random.choice(trigger_fallbacks)
