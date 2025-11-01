from typing import List, Dict
from domain.entity.profile import UserProfile


class ContextService:
    @staticmethod
    def create_personalized_prompt(base_prompt: str, profile: UserProfile = None) -> str:
        """Создание персонализированного промпта"""
        personalized_prompt = base_prompt

        if profile:
            if profile.name:
                personalized_prompt += f"\n\nИмя пользователя: {profile.name}"
            if profile.interests:
                personalized_prompt += f"\nИнтересы пользователя: {profile.interests}"
            if profile.mood:
                personalized_prompt += f"\nПоследнее известное настроение: {profile.mood}"

        return personalized_prompt

    @staticmethod
    def prepare_messages_for_ai(system_prompt: str, context_messages: List[Dict], current_message: str) -> List[Dict]:
        """Подготовка сообщений для отправки в AI"""
        messages = [{"role": "system", "content": system_prompt}]

        for msg in context_messages:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": current_message})

        return messages