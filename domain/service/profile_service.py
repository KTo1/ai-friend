import re
from typing import Tuple, Optional, List


class ProfileService:
    # Список распространенных русских имен для проверки
    COMMON_RUSSIAN_NAMES = {
        'анна', 'мария', 'елена', 'ольга', 'наталья', 'ирина', 'светлана', 'татьяна', 'евгения', 'юлия',
        'александр', 'сергей', 'дмитрий', 'андрей', 'алексей', 'михаил', 'евгений', 'иван', 'максим', 'владимир',
        'артем', 'никита', 'павел', 'роман', 'константин', 'владислав', 'кирилл', 'станислав', 'вячеслав', 'григорий',
        'марк', 'лев', 'федор', 'георгий', 'петр', 'борис', 'геннадий', 'валерий', 'василий', 'виктор'
    }

    # Список стоп-слов которые не могут быть именами
    STOP_WORDS = {
        'пошел', 'пришел', 'ушел', 'шел', 'ехал', 'сидел', 'стоял', 'лежал', 'бежал', 'прыгал',
        'спал', 'бодрствовал', 'работал', 'учился', 'отдыхал', 'гулял', 'смотрел', 'слушал', 'читал',
        'писал', 'рисовал', 'играл', 'плавал', 'бегал', 'прыгал', 'танцевал', 'пел', 'говорил'
    }

    @staticmethod
    def extract_profile_info(message: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
        """Извлечение информации о профиле из сообщения с улучшенным парсингом"""
        name = None
        age = None
        interests = None
        mood = None

        text = message.lower().strip()

        # 1. Парсинг имени с улучшенными паттернами
        name = ProfileService._extract_name_advanced(text)

        # 2. Парсинг возраста
        age = ProfileService._extract_age(text)

        # 3. Парсинг интересов
        interests = ProfileService._extract_interests(text)

        # 4. Парсинг настроения
        mood = ProfileService._extract_mood(text)

        return name, age, interests, mood

    @staticmethod
    def _extract_name_advanced(text: str) -> Optional[str]:
        """Улучшенный парсинг имени с проверкой контекста"""

        # Паттерны с приоритетом (от самых надежных к менее надежным)
        patterns = [
            # 1. Явные указания имени (самые надежные)
            (r'(?:меня\s+зовут|мое\s+имя|зовут\s+меня)\s+([а-яa-z]{2,20})', 1.0),
            (r'(?:имя\s+)?([а-яa-z]{2,20})(?:\s+имя)', 0.9),

            # 2. Конструкции с "я" но с проверкой контекста
            (r'я\s+([а-яa-z]{2,20})(?:\s+(?:и мне|мне|а мне))', 0.8),
            (r'я\s+([а-яa-z]{2,20})(?=[\.!?]|$)', 0.6),  # Только в конце предложения

            # 3. Представления в диалоге
            (r'(?:привет|здравствуй|здравствуйте)[^.!?]*([а-яa-z]{2,20})', 0.7),

            # 4. Указания в кавычках или с большой буквы в оригинале
            (r'(?:имя\s+)?["«]([а-яa-z]{2,20})["»]', 0.9),
        ]

        best_candidate = None
        best_score = 0

        for pattern, base_score in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                candidate = match.group(1).capitalize()
                candidate_lower = candidate.lower()

                # Проверяем кандидата
                candidate_score = base_score

                # Повышаем score если это распространенное имя
                if candidate_lower in ProfileService.COMMON_RUSSIAN_NAMES:
                    candidate_score += 0.3

                # Понижаем score если это стоп-слово
                if candidate_lower in ProfileService.STOP_WORDS:
                    candidate_score -= 0.5

                # Проверяем длину имени (имена обычно 2-15 букв)
                if len(candidate) < 2:
                    candidate_score -= 0.3
                elif len(candidate) > 15:
                    candidate_score -= 0.2

                # Проверяем наличие цифр (в именах цифр не бывает)
                if any(char.isdigit() for char in candidate):
                    candidate_score -= 0.5

                # Сохраняем лучшего кандидата
                if candidate_score > best_score and candidate_score > 0.5:
                    best_candidate = candidate
                    best_score = candidate_score

        return best_candidate

    @staticmethod
    def _extract_age(text: str) -> Optional[int]:
        """Извлечение возраста"""
        # Более строгие паттерны для возраста
        age_patterns = [
            r'(?:мне|исполнилось|будет)\s+(\d{1,3})\s+(?:год|лет|года)',
            r'(?:возраст|лет)\s+(\d{1,3})',
            r'(\d{1,3})\s+(?:год|лет|года)(?:\s+мне)?',
        ]

        for pattern in age_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    age = int(match.group(1))
                    if 1 <= age <= 120:  # Реалистичный возраст
                        return age
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extract_interests(text: str) -> Optional[str]:
        """Извлечение интересов с проверкой контекста"""
        interest_indicators = [
            ('интересуюсь', 1.0),
            ('увлекаюсь', 1.0),
            ('нравится', 0.8),
            ('люблю', 0.7),
            ('занимаюсь', 0.9),
            ('хобби', 1.0),
        ]

        for indicator, confidence in interest_indicators:
            if indicator in text:
                # Ищем текст после индикатора до конца предложения
                start_idx = text.find(indicator) + len(indicator)
                sentence_end = min(
                    text.find('.', start_idx) if '.' in text[start_idx:] else len(text),
                    text.find('!', start_idx) if '!' in text[start_idx:] else len(text),
                    text.find('?', start_idx) if '?' in text[start_idx:] else len(text),
                    text.find(',', start_idx) if ',' in text[start_idx:] else len(text),
                    text.find('\n', start_idx) if '\n' in text[start_idx:] else len(text)
                )

                if sentence_end > start_idx:
                    interests = text[start_idx:sentence_end].strip(' ,')
                    if interests and len(interests) > 2:  # Минимальная длина интереса
                        return interests.capitalize()

        return None

    @staticmethod
    def _extract_mood(text: str) -> Optional[str]:
        """Извлечение настроения"""
        mood_mapping = {
            'грустно': 'грустное',
            'грусть': 'грустное',
            'печально': 'грустное',
            'весело': 'веселое',
            'радостно': 'радостное',
            'рад': 'радостное',
            'счастлив': 'счастливое',
            'одиноко': 'одинокое',
            'скучно': 'скучное',
            'тревожно': 'тревожное',
            'спокойно': 'спокойное',
            'устал': 'уставшее',
            'устала': 'уставшее',
            'злой': 'злое',
            'злая': 'злое',
            'раздражен': 'раздраженное',
            'раздражена': 'раздраженное',
        }

        # Ищем слова настроения в контексте
        for mood_word, mood_value in mood_mapping.items():
            # Проверяем что это отдельное слово или в контексте настроения
            if (f" {mood_word} " in f" {text} " or
                    text.startswith(mood_word + " ") or
                    text.endswith(" " + mood_word) or
                    f"настроение {mood_word}" in text or
                    f"чувствую себя {mood_word}" in text):
                return mood_value

        return None

    @staticmethod
    def validate_name_candidate(name: str) -> bool:
        """Проверить что кандидат на имя действительно похож на имя"""
        name_lower = name.lower()

        # Проверка стоп-слов
        if name_lower in ProfileService.STOP_WORDS:
            return False

        # Проверка длины
        if len(name) < 2 or len(name) > 20:
            return False

        # Проверка на цифры
        if any(char.isdigit() for char in name):
            return False

        # Проверка что первая буква заглавная (в оригинале)
        if not name[0].isupper():
            return False

        # Проверка что это распространенное имя (не обязательная, но повышает уверенность)
        if name_lower in ProfileService.COMMON_RUSSIAN_NAMES:
            return True

        # Если не распространенное имя, но прошло другие проверки - ок
        return True