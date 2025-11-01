import re
from typing import Tuple, Optional


class ProfileService:
    @staticmethod
    def extract_profile_info(message: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
        """Извлечение информации о профиле из сообщения"""
        name = None
        age = None
        interests = None
        mood = None

        text = message.lower()

        # Извлечение имени
        name_patterns = [
            r'меня зовут\s+([а-яa-z]+)',
            r'зовут\s+([а-яa-z]+)',
            r'я\s+([а-яa-z]+)',
            r'мое имя\s+([а-яa-z]+)'
        ]

        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).capitalize()
                break

        # Извлечение возраста
        age_match = re.search(r'мне\s+(\d+)\s+лет?', text)
        if age_match:
            age = int(age_match.group(1))

        # Извлечение интересов
        interest_indicators = ['интересуюсь', 'нравится', 'люблю', 'увлекаюсь']
        for indicator in interest_indicators:
            if indicator in text:
                interest_start = text.find(indicator) + len(indicator)
                interests = message[interest_start:].strip('.,!?')
                break

        # Извлечение настроения
        mood_words = {
            'грустно': 'грустное',
            'весело': 'веселое',
            'одиноко': 'одинокое',
            'рад': 'радостное',
            'счастлив': 'счастливое',
            'тревожно': 'тревожное',
            'спокойно': 'спокойное'
        }

        for mood_word, mood_value in mood_words.items():
            if mood_word in text:
                mood = mood_value
                break

        return name, age, interests, mood