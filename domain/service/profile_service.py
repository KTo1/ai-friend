import json
import re
from typing import Tuple, Optional, List, Any
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.logging import StructuredLogger


class ProfileService:
    """
    Сервис для извлечения и управления информацией профиля пользователя,
    используя LLM для семантического анализа.
    """

    def __init__(self, ai_client: AIClientInterface):
        self.ai_client = ai_client
        self.logger = StructuredLogger("profile_service")

        # Ключевые слова, которые запускают анализ профиля
        self.trigger_keywords = [
            'зовут', 'имя', 'мне', 'лет', 'год', 'года',
            'интересуюсь', 'увлекаюсь', 'нравится', 'люблю',
            'хобби', 'настроение', 'чувствую', 'грустно',
            'весело', 'рад', 'зол', 'устал'
        ]

    def _build_extraction_prompt(self, message: str) -> List[dict]:
        """
        Создает промпт для LLM для извлечения данных профиля в формате JSON.
        """

        system_prompt = """
Ты — сверхточный и быстрый инструмент для извлечения данных (ETL).
Твоя задача — проанализировать ОДНО сообщение от пользователя и извлечь из него сущности, связанные с его профилем.

Ты ДОЛЖЕН ответить ИСКЛЮЧИТЕЛЬНО в формате JSON.
Если какая-то информация отсутствует, верни `null` для этого поля.
Не добавляй никаких пояснений, только JSON.

Формат JSON:
{
  "name": "Имя пользователя (string, null если нет)",
  "age": "Возраст пользователя (integer, null если нет)",
  "interests": "Список интересов (list of strings, [] если нет)",
  "mood": "Настроение пользователя (string, null если нет)"
  "gender": "Пол пользователя, строго: мужчина или женщина (string, null если нет)"
  "instruction_addition": "При извлечении пола (gender) анализируй имя пользователя. Для русских имен используй родовые окончания 
Если имя явно указывает на пол определи его. Если пол по имени неочевиден или имя отсутствует, верни null."
}

ПРИМЕРЫ:
---
Сообщение: "Меня зовут Вася, мне 25 лет."
Ответ:
{
  "name": "Вася",
  "age": 25,
  "interests": [],
  "mood": null
}
---
Сообщение: "Я люблю программировать и гулять"
Ответ:
{
  "name": null,
  "age": null,
  "interests": ["программирование", "прогулки"],
  "mood": null
}
---
Сообщение: "Сегодня мне что-то грустно"
Ответ:
{
  "name": null,
  "age": null,
  "interests": [],
  "mood": "грустное"
}
---
Сообщение: "Привет, как дела?"
Ответ:
{
  "name": null,
  "age": null,
  "interests": [],
  "mood": null
}
---
"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Сообщение: \"{message}\""}
        ]

    def _message_contains_triggers(self, message: str) -> bool:
        """
        Проверяет, содержит ли сообщение триггерные слова для
        запуска дорогостоящего LLM-анализа.
        """
        text = message.lower()
        for keyword in self.trigger_keywords:
            if keyword in text:
                return True
        return False

    async def extract_profile_info_llm(self, message: str) -> Tuple[
        Optional[str], Optional[int], Optional[str], Optional[str], Optional[str]]:
        """
        Извлечение информации о профиле из сообщения с помощью LLM.
        Возвращает (name, age, interests_str, mood).
        """

        # 1. Проверяем, нужно ли вообще запускать LLM
        if not self._message_contains_triggers(message):
            return None, None, None, None, None

        # 2. Строим промпт и вызываем LLM
        prompt = self._build_extraction_prompt(message)

        try:
            # Используем быстрый и дешевый AI-вызов
            response_json_str = await self.ai_client.generate_response(
                prompt,
                max_tokens=200,
                temperature=0.0  # Нам нужна точность, а не креативность
            )

            # 3. Парсим JSON
            # LLM иногда заворачивает JSON в ```json ... ```
            if "```" in response_json_str:
                response_json_str = re.sub(r'```json\n(.*?)\n```', r'\1', response_json_str, flags=re.DOTALL)
                response_json_str = re.sub(r'```(.*?)\n```', r'\1', response_json_str, flags=re.DOTALL)

            data = json.loads(response_json_str.strip())

            name = data.get('name')
            age = data.get('age')
            interests_list = data.get('interests')
            mood = data.get('mood')
            gender = data.get('gender')

            # 4. Форматируем вывод
            interests_str = ", ".join(interests_list) if interests_list else None

            log_data = {
                "extracted_name": name if name else "null",
                "extracted_age": str(age) if age is not None else "null",
                "extracted_mood": mood if mood else "null",
                "extracted_interests": ", ".join(interests_list) if interests_list else "null",
                "extracted_gender": gender if gender else "null",
            }

            # Логируем успешный парсинг с безопасными строками
            if name or age or interests_str or mood:
                self.logger.info("LLM extracted profile data", extra=log_data)

            return name, age, interests_str, mood, gender

        except Exception as e:
            self.logger.error(
                f"Failed to parse profile info from LLM response: {e}",
                extra={"llm_response": response_json_str}
            )
            return None, None, None, None, None