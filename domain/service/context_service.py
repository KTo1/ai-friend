from typing import List, Dict


class ContextService:
    @staticmethod
    def prepare_messages_for_ai(system_prompt: str, context_messages: List[Dict], current_message: str) -> List[Dict]:
        """Подготовка сообщений для отправки в AI"""

        messages = [{"role": "system", "content": system_prompt}]

        for msg in context_messages:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": current_message})

        return messages