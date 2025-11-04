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
            # Используем LLM для генерации контекстных сообщений
            system_prompt = self._build_system_prompt(profile, activity, trigger, conversation_context)
            user_prompt = self._build_user_prompt(trigger)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Добавляем контекст разговора для персонализации
            if conversation_context:
                messages.extend(conversation_context[-3:])  # Последние 3 сообщения

            response = await self.ai_client.generate_response(
                messages,
                max_tokens=100,
                temperature=0.8
            )

            if response and self._is_valid_proactive_message(response):
                self.logger.info(f"✅ Generated proactive message for user {user_id}")
                return response.strip()
            else:
                return self._get_fallback_message(trigger, profile)

        except Exception as e:
            self.logger.error(f"❌ Error generating proactive message: {e}")
            return self._get_fallback_message(trigger, profile)

    def _build_system_prompt(self, profile: UserProfile, activity: UserActivity,
                             trigger: ProactiveTrigger, context: List[Dict]) -> str:
        """Построить системный промпт"""

        base_prompt = """Ты — Айна, заботливый виртуальный друг. Сгенерируй естественное проактивное сообщение.

Требования:
- Естественное и непринужденное
- Теплое и поддерживающее  
- Короткое (1-2 предложения)
- Соответствующее времени суток и контексту
- Не навязчивое

Стиль: дружеский, заботливый, с легким использованием эмодзи"""

        # Добавляем информацию о пользователе
        if profile and profile.name:
            base_prompt += f"\n\nИмя пользователя: {profile.name}"
        if profile and profile.interests:
            base_prompt += f"\nИнтересы: {profile.interests}"

        # Добавляем информацию о времени
        local_time = activity.get_local_time()
        time_info = "утро" if 5 <= local_time.hour < 12 else "день" if 12 <= local_time.hour < 18 else "вечер"
        base_prompt += f"\nСейчас {time_info}, время: {local_time.strftime('%H:%M')}"

        return base_prompt

    def _build_user_prompt(self, trigger: ProactiveTrigger) -> str:
        """Построить пользовательский промпт"""

        prompts = {
            ProactiveTrigger.MORNING_GREETING: "Придумай естественное утреннее приветствие для друга",
            ProactiveTrigger.EVENING_CHECK: "Напиши вечернее сообщение, чтобы спросить как прошел день",
            ProactiveTrigger.INACTIVITY_REMINDER: "Напиши легкое напоминание о себе после периода молчания",
            ProactiveTrigger.FOLLOW_UP: "Придумай вопрос для продолжения нашего разговора"
        }

        return prompts.get(trigger, "Напиши естественное сообщение для поддержания общения")

    def _is_valid_proactive_message(self, message: str) -> bool:
        """Проверить что сообщение адекватное"""
        return message and len(message.strip()) > 10 and len(message) < 200

    def _get_fallback_message(self, trigger: ProactiveTrigger, profile: UserProfile) -> str:
        """Запасные сообщения"""
        name = profile.name if profile and profile.name else ""

        fallbacks = {
            ProactiveTrigger.MORNING_GREETING: f"Доброе утро{', ' + name if name else ''}! ☀️ Как ты сегодня проснулся?",
            ProactiveTrigger.EVENING_CHECK: f"Привет{', ' + name if name else ''}! Как прошел твой день? 🌙",
            ProactiveTrigger.INACTIVITY_REMINDER: f"Привет{', ' + name if name else ''}! Соскучилась по нашим разговорам 💫",
            ProactiveTrigger.FOLLOW_UP: f"Кстати{', ' + name if name else ''}... Как твое настроение? 😊"
        }
        return fallbacks.get(trigger, f"Привет{', ' + name if name else ''}! Как твои дела? 😊")