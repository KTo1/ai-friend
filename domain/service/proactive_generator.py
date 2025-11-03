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

    async def generate_proactive_message(self,
                                         user_id: int,
                                         profile: UserProfile,
                                         activity: UserActivity,
                                         trigger: ProactiveTrigger,
                                         conversation_context: List[Dict]) -> Optional[str]:
        """Сгенерировать проактивное сообщение через LLM на основе контекста"""

        try:
            system_prompt = self._build_system_prompt(profile, activity, trigger, conversation_context)
            messages = [{"role": "system", "content": system_prompt}]

            # Добавляем контекст разговора для персонализации
            if conversation_context:
                messages.extend(conversation_context[-5:])  # Последние 5 сообщений

            user_prompt = self._build_user_prompt(trigger)
            messages.append({"role": "user", "content": user_prompt})

            response = await self.ai_client.generate_response(
                messages,
                max_tokens=150,
                temperature=0.8  # Более креативные ответы
            )

            # Проверяем что ответ адекватный
            if self._is_valid_proactive_message(response):
                self.logger.info(
                    f"Generated proactive message for user {user_id}",
                    extra={'trigger': trigger.value, 'response_length': len(response)}
                )
                return response.strip()
            else:
                self.logger.warning(f"Generated invalid proactive message: {response}")
                return None

        except Exception as e:
            self.logger.error(f"Error generating proactive message: {e}")
            return self._get_fallback_message(trigger)

    def _build_system_prompt(self, profile: UserProfile, activity: UserActivity,
                             trigger: ProactiveTrigger, context: List[Dict]) -> str:
        """Построить системный промпт для генерации проактивных сообщений"""

        base_prompt = """Ты — Айна, заботливый виртуальный друг. Твоя задача — генерировать естественные, теплые проактивные сообщения для поддержания общения.

Требования к сообщениям:
- Естественные и непринужденные
- Теплые и поддерживающие
- Короткие (1-2 предложения)
- Соответствующие контексту и времени суток
- Не навязчивые
- Учитывающие историю общения

Стиль: дружеский, заботливый, с легким использованием эмодзи"""

        # Добавляем информацию о пользователе
        if profile.name:
            base_prompt += f"\n\nИмя пользователя: {profile.name}"
        if profile.interests:
            base_prompt += f"\nИнтересы пользователя: {profile.interests}"

        # Добавляем информацию о времени
        local_time = activity.get_local_time()
        base_prompt += f"\nТекущее время у пользователя: {local_time.strftime('%H:%M')}"

        # Добавляем информацию о триггере
        trigger_descriptions = {
            ProactiveTrigger.MORNING_GREETING: "утреннее приветствие",
            ProactiveTrigger.EVENING_CHECK: "вечерняя проверка",
            ProactiveTrigger.INACTIVITY_REMINDER: "напоминание после периода неактивности",
            ProactiveTrigger.FOLLOW_UP: "продолжение предыдущего разговора",
            ProactiveTrigger.WEEKLY_CHECKIN: "недельная проверка"
        }

        base_prompt += f"\nТип сообщения: {trigger_descriptions.get(trigger, 'проактивное общение')}"

        return base_prompt

    def _build_user_prompt(self, trigger: ProactiveTrigger) -> str:
        """Построить пользовательский промпт"""

        prompts = {
            ProactiveTrigger.MORNING_GREETING: "Придумай естественное утреннее приветствие. Будь легкой и позитивной!",
            ProactiveTrigger.EVENING_CHECK: "Напиши вечернее сообщение, чтобы спросить как прошел день. Будь заботливой!",
            ProactiveTrigger.INACTIVITY_REMINDER: "Напиши легкое напоминание о себе после периода молчания. Без давления!",
            ProactiveTrigger.FOLLOW_UP: "Придумай вопрос для продолжения нашего последнего разговора. Естественно и с интересом!",
            ProactiveTrigger.WEEKLY_CHECKIN: "Спроси как прошел день или неделя. Прояви участие!"
        }

        return prompts.get(trigger, "Напиши естественное сообщение для поддержания общения")

    def _is_valid_proactive_message(self, message: str) -> bool:
        """Проверить что сгенерированное сообщение адекватное"""
        if not message or len(message.strip()) < 10:
            return False

        # Проверяем на слишком длинные сообщения
        if len(message) > 300:
            return False

        # Проверяем на неадекватный контент
        invalid_phrases = ["как AI", "как искусственный интеллект", "как языковая модель"]
        return not any(phrase in message.lower() for phrase in invalid_phrases)

    def _get_fallback_message(self, trigger: ProactiveTrigger) -> str:
        """Запасные сообщения если LLM не сработал"""
        fallbacks = {
            ProactiveTrigger.MORNING_GREETING: "Доброе утро! ☀️ Как ты сегодня проснулся?",
            ProactiveTrigger.EVENING_CHECK: "Привет! Как прошел твой день? 🌙",
            ProactiveTrigger.INACTIVITY_REMINDER: "Привет! Как твои дела? Соскучилась по нашим разговорам 💫",
            ProactiveTrigger.FOLLOW_UP: "Кстати, хотела спросить... Как твое настроение? 😊",
            ProactiveTrigger.WEEKLY_CHECKIN: "Привет! Что нового в твоей жизни? 🎯"
        }
        return fallbacks.get(trigger, "Привет! Как твои дела? 😊")