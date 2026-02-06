#!/usr/bin/env python3
"""
📊 Экспорт диалогов для анализа промптов персонажей с умной структурой

Структура экспорта:
  character_name/
    ├── TASK.txt                    # Главная задача для AI
    ├── current_prompt.txt          # Текущий промпт персонажа
    ├── statistics.txt              # Статистика по диалогам
    ├── dialogue_001_user_12345.txt # Диалог 1 (пользователь 12345)
    ├── dialogue_002_user_67890.txt # Диалог 2 (пользователь 67890)
    └── ...                         # Все остальные диалоги
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import argparse
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import RealDictCursor


# ============================================================================
# 📄 export_conversations_for_analysis.py
# ============================================================================

@dataclass
class DatabaseConfig:
    """Конфигурация подключения к базе данных"""
    host: str = "localhost"
    port: int = 5433
    database: str = "ai-friend"
    user: str = "not_postgres"
    password: str = "_koa3f7uN-JLH3x@1vR$"

    def get_connection_string(self) -> str:
        """Получить строку подключения PostgreSQL"""
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"


@dataclass
class ConversationMessage:
    """Сообщение из диалога"""
    role: str  # 'user' или 'assistant'
    content: str
    timestamp: datetime
    message_id: int


@dataclass
class CharacterInfo:
    """Информация о персонаже"""
    id: int
    name: str
    description: str
    system_prompt: str
    avatar_mime_type: str
    is_active: bool


@dataclass
class UserDialogue:
    """Диалог конкретного пользователя с персонажем"""
    user_id: int
    character_id: int
    character_name: str
    messages: List[ConversationMessage]
    total_messages: int
    first_message_date: datetime
    last_message_date: datetime
    user_info: Optional[Dict] = None


class ConversationExporter:
    """Экспортер диалогов из базы данных"""

    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self.connection = None
        self.cursor = None

    def connect(self):
        """Подключиться к базе данных"""
        try:
            self.connection = psycopg2.connect(
                self.db_config.get_connection_string(),
                cursor_factory=RealDictCursor
            )
            self.cursor = self.connection.cursor()
            print(f"✅ Подключение к БД установлено: {self.db_config.database}")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            return False

    def disconnect(self):
        """Отключиться от базы данных"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        print("🔌 Отключение от БД")

    def get_all_characters(self) -> Dict[int, CharacterInfo]:
        """Получить всех персонажей из базы"""
        query = """
                SELECT id, \
                       name, \
                       description, \
                       system_prompt,
                       avatar_mime_type, \
                       is_active
                FROM characters
                WHERE is_active = TRUE
                ORDER BY id \
                """

        self.cursor.execute(query)
        characters = {}

        for row in self.cursor.fetchall():
            character = CharacterInfo(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                system_prompt=row['system_prompt'],
                avatar_mime_type=row['avatar_mime_type'],
                is_active=row['is_active']
            )
            characters[character.id] = character

        print(f"📊 Загружено персонажей: {len(characters)}")
        return characters

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе"""
        query = """
                SELECT user_id, \
                       username, \
                       first_name, \
                       last_name,
                       created_at, \
                       last_seen, \
                       is_admin, \
                       is_blocked
                FROM users
                WHERE user_id = %s \
                """

        try:
            self.cursor.execute(query, (user_id,))
            row = self.cursor.fetchone()
            if row:
                return dict(row)
        except Exception as e:
            print(f"⚠️ Ошибка получения информации о пользователе {user_id}: {e}")

        return None

    def get_conversations_for_character(self, character_id: int) -> List[UserDialogue]:
        """Получить все диалоги для конкретного персонажа"""
        query = """
                SELECT cc.id, \
                       cc.user_id, \
                       cc.character_id, \
                       cc.role,
                       cc.content, \
                       cc.timestamp, \
                       c.name as character_name
                FROM conversation_context cc
                         JOIN characters c ON cc.character_id = c.id
                WHERE cc.character_id = %s
                  AND cc.deleted_at IS NULL
                ORDER BY cc.user_id, cc.timestamp ASC \
                """

        self.cursor.execute(query, (character_id,))
        rows = self.cursor.fetchall()

        # Группируем по пользователям
        user_dialogues = {}

        for row in rows:
            user_id = row['user_id']

            if user_id not in user_dialogues:
                user_dialogues[user_id] = {
                    'user_id': user_id,
                    'character_id': character_id,
                    'character_name': row['character_name'],
                    'messages': [],
                    'first_message_date': None,
                    'last_message_date': None
                }

            message = ConversationMessage(
                role=row['role'],
                content=row['content'],
                timestamp=row['timestamp'],
                message_id=row['id']
            )

            user_dialogues[user_id]['messages'].append(message)

            # Обновляем даты
            if not user_dialogues[user_id]['first_message_date'] or message.timestamp < user_dialogues[user_id][
                'first_message_date']:
                user_dialogues[user_id]['first_message_date'] = message.timestamp

            if not user_dialogues[user_id]['last_message_date'] or message.timestamp > user_dialogues[user_id][
                'last_message_date']:
                user_dialogues[user_id]['last_message_date'] = message.timestamp

        # Преобразуем в объекты UserDialogue
        result = []
        for user_id, data in user_dialogues.items():
            dialogue = UserDialogue(
                user_id=user_id,
                character_id=data['character_id'],
                character_name=data['character_name'],
                messages=data['messages'],
                total_messages=len(data['messages']),
                first_message_date=data['first_message_date'],
                last_message_date=data['last_message_date'],
                user_info=self.get_user_info(user_id)
            )
            result.append(dialogue)

        return result

    def get_all_conversations(self) -> Dict[int, Dict]:
        """Получить все диалоги для всех персонажей"""
        characters = self.get_all_characters()
        all_conversations = {}

        for character_id, character in characters.items():
            print(f"📖 Загрузка диалогов для персонажа: {character.name} (ID: {character_id})")
            conversations = self.get_conversations_for_character(character_id)
            all_conversations[character_id] = {
                'character': character,
                'dialogues': conversations,
                'total_dialogues': len(conversations),
                'total_messages': sum(len(d.messages) for d in conversations)
            }
            print(
                f"   → Загружено диалогов: {len(conversations)}, сообщений: {sum(len(d.messages) for d in conversations)}")

        return all_conversations


class DialogueExporter:
    """Экспортер диалогов в структурированные файлы"""

    def __init__(self, output_dir: str = "./conversation_analysis"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_task_file(self, character: CharacterInfo, dialogues: List[UserDialogue], character_dir: Path):
        """Создать главный файл с задачей для AI"""

        # Статистика
        total_users = len(dialogues)
        total_messages = sum(len(d.messages) for d in dialogues)
        avg_messages_per_user = total_messages / total_users if total_users > 0 else 0

        # Формируем список файлов с диалогами
        dialogue_files = []
        for i, dialogue in enumerate(dialogues, 1):
            filename = f"dialogue_{i:03d}_user_{dialogue.user_id}.txt"
            dialogue_files.append(filename)

        task_content = f"""# 🎯 ЗАДАЧА: Анализ диалогов и улучшение промпта персонажа

        ## 📋 О ПРОЕКТЕ
        Вы - эксперт по промпт-инжинирингу и анализу диалогов. Вам предоставлены реальные диалоги пользователей с ИИ-персонажем.
        
        ## 🤖 ПЕРСОНАЖ
        **Имя:** {character.name}
        **Описание:** {character.description}
        
        ## 📊 СТАТИСТИКА ДИАЛОГОВ
        - **Всего пользователей:** {total_users}
        - **Всего сообщений:** {total_messages}
        - **Среднее сообщений на пользователя:** {avg_messages_per_user:.1f}
        - **Дата экспорта:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        ## 📁 ПРЕДОСТАВЛЕННЫЕ МАТЕРИАЛЫ
        
        ### 1. ТЕКУЩИЙ ПРОМПТ ПЕРСОНАЖА
        Файл: `current_prompt.txt`
        Содержит текущий системный промпт, который используется персонажем.
        
        ### 2. ДИАЛОГИ ПОЛЬЗОВАТЕЛЕЙ
        Всего файлов с диалогами: {len(dialogue_files)}
        
        Список файлов:
        {chr(10).join(f'- `{f}`' for f in dialogue_files)}
        
        Каждый файл содержит полный диалог одного пользователя с персонажем в формате:
        [ВРЕМЯ] РОЛЬ: ТЕКСТ

        ### 3. СТАТИСТИКА
        Файл: `statistics.txt`
        Подробная статистика по всем диалогам.

        ## 🎯 ЗАДАНИЕ

        ### ЦЕЛЬ
        Проанализировать ВСЕ предоставленные диалоги и предложить конкретные улучшения для промпта персонажа.

        ### ЧТО АНАЛИЗИРОВАТЬ

        1. **📖 СОДЕРЖАНИЕ ДИАЛОГОВ:**
           - Прочитайте ВСЕ файлы с диалогами
           - Обратите внимание на паттерны общения
           - Отметьте успешные и неудачные взаимодействия

        2. **🤖 АНАЛИЗ ТЕКУЩЕГО ПРОМПТА:**
           - Прочитайте файл `current_prompt.txt`
           - Оцените, насколько промпт соответствует реальным диалогам
           - Найдите расхождения между задуманным и реальным поведением

        3. **💡 КЛЮЧЕВЫЕ ВОПРОСЫ ДЛЯ АНАЛИЗА:**
           - Что пользователи ожидают от персонажа?
           - Какие темы обсуждаются чаще всего?
           - Как персонаж реагирует на разные типы сообщений?
           - Где теряется контекст разговора?
           - Какие эмоциональные реакции ценят пользователи?
           - Что можно улучшить в стиле общения?

            3.1. **Тон и стиль общения:**
               - Соответствует ли стиль ответов бота характеру персонажа "{character.name}"?
               - Поддерживается ли единый тон на протяжении всего диалога?
               - Как пользователь реагирует на стиль общения бота?

            3.2. **Контекст и память:**
               - Сохраняется ли контекст разговора между сообщениями?
               - Используются ли ранее упомянутые факты о пользователе?
               - Есть ли повторения или противоречия в ответах?

            3.3. **Эмоциональная составляющая:**
               - Насколько ответы бота эмоционально окрашены?
               - Соответствует ли уровень эмпатии ожиданиям от персонажа?
               - Как бот реагирует на эмоциональные сообщения пользователя?

            3.4. **Содержательность ответов:**
               - Даются ли развернутые, содержательные ответы?
               - Есть ли шаблонные или общие фразы?
               - Насколько ответы соответствуют запросам пользователя?
            
            3.5. **Предложения по улучшению:**
               - Какие аспекты промпта нужно усилить?
               - Какие слабые места в ответах бота?
               - Конкретные примеры улучшений из этого диалога.
   
        4. **🎭 ЛИЧНОСТЬ ПЕРСОНАЖА:**
           - Соответствует ли текущая личность ожиданиям пользователей?
           - Какие черты характера "работают" лучше всего?
           - Что стоит усилить или ослабить?

        ## 📝 ТРЕБОВАНИЯ К РЕЗУЛЬТАТУ

        ### 1. КРАТКИЙ АНАЛИЗ (максимум 500 слов)
        - Основные выводы по всем диалогам
        - Сильные и слабые стороны текущего промпта
        - Ключевые инсайты

        ### 2. ТОП-10 КОНКРЕТНЫХ УЛУЧШЕНИЙ
        Пронумерованный список конкретных изменений для промпта. Например:
        1. "Добавить реакцию на комплименты"
        2. "Улучшить обработку вопросов о хобби"
        3. "Добавить больше эмоциональных реакций"

        ### 3. ОБНОВЛЕННЫЙ ПРОМПТ
        Полный текст нового улучшенного промпта, включая ВСЕ предложенные изменения.

        ### 4. ОБЪЯСНЕНИЯ
        Краткие пояснения к каждому изменению:
        - Почему это важно?
        - На основе какого диалога/паттерна предложено?
        - Какой эффект ожидается?

        ## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

        1. **УЧИТЫВАЙТЕ ВСЕ ДИАЛОГИ** - каждый файл содержит ценный опыт
        2. **БУДЬТЕ КОНКРЕТНЫ** - предлагайте конкретные формулировки для промпта
        3. **СОХРАНИТЕ СИЛЬНЫЕ СТОРОНЫ** - не ломайте то, что уже хорошо работает
        4. **УЧИТЫВАЙТЕ КОНТЕКСТ** - промпт должен работать в рамках Telegram-бота
        5. **ОРИЕНТИРУЙТЕСЬ НА ПОЛЬЗОВАТЕЛЕЙ** - улучшения должны быть основаны на реальных диалогах

        ## 🚀 НАЧИНАЙТЕ РАБОТУ

        1. Прочитайте файл `current_prompt.txt`
        2. Изучите ВСЕ файлы с диалогами (от `dialogue_001_...` до `dialogue_{len(dialogue_files):03d}_...`)
        3. Проанализируйте статистику в `statistics.txt`
        4. Выполните задание, следуя требованиям выше

        Удачи! Ваш анализ поможет сделать персонажа лучше для тысяч пользователей.
        """

        task_file = character_dir / "TASK.txt"
        with open(task_file, 'w', encoding='utf-8') as f:
            f.write(task_content)

        print(f"  📋 Создан файл задачи: TASK.txt ({len(task_content):,} символов)")
        return dialogue_files

    def export_dialogue_file(self, character: CharacterInfo, dialogue: UserDialogue,
                             dialogue_index: int, character_dir: Path):
        """Экспортировать один диалог в отдельный файл"""

        # Определяем имя файла
        filename = f"dialogue_{dialogue_index:03d}_user_{dialogue.user_id}.txt"
        filepath = character_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            # Заголовок
            f.write(f"# Диалог #{dialogue_index}: Пользователь ID {dialogue.user_id}\n")
            f.write(f"# Персонаж: {character.name}\n")
            f.write(f"# Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            # Информация о пользователе
            if dialogue.user_info:
                f.write("👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:\n")
                f.write("-" * 40 + "\n")

                username = dialogue.user_info.get('username')
                first_name = dialogue.user_info.get('first_name')
                last_name = dialogue.user_info.get('last_name')

                if username:
                    f.write(f"Username: @{username}\n")
                if first_name or last_name:
                    name = f"{first_name or ''} {last_name or ''}".strip()
                    if name:
                        f.write(f"Имя: {name}\n")

                if dialogue.user_info.get('created_at'):
                    created = dialogue.user_info['created_at']
                    if isinstance(created, str):
                        created = created[:19]
                    f.write(f"Зарегистрирован: {created}\n")

                f.write("\n")

            # Статистика диалога
            f.write("📊 СТАТИСТИКА ДИАЛОГА:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Всего сообщений: {dialogue.total_messages}\n")
            f.write(f"Дата первого сообщения: {dialogue.first_message_date}\n")
            f.write(f"Дата последнего сообщения: {dialogue.last_message_date}\n")

            if dialogue.last_message_date and dialogue.first_message_date:
                duration = dialogue.last_message_date - dialogue.first_message_date
                f.write(f"Длительность общения: {duration.days} дней\n")

            f.write("\n" + "=" * 60 + "\n\n")
            f.write("💬 ПОЛНЫЙ ТЕКСТ ДИАЛОГА:\n\n")

            # Все сообщения диалога
            for i, msg in enumerate(dialogue.messages, 1):
                timestamp_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")

                if msg.role == 'user':
                    f.write(f"[{timestamp_str}] 👤 ПОЛЬЗОВАТЕЛЬ:\n")
                else:
                    f.write(f"[{timestamp_str}] 🤖 {character.name.upper()}:\n")

                # Разбиваем длинные сообщения на строки
                lines = msg.content.split('\n')
                for line in lines:
                    if line.strip():
                        f.write(f"  {line}\n")
                    else:
                        f.write("\n")

                f.write("\n")
                f.write("-" * 40 + "\n\n")

            # Итог
            f.write(f"✅ КОНЕЦ ДИАЛОГА #{dialogue_index}\n")
            f.write(f"Всего сообщений: {dialogue.total_messages}\n")

        return filename

    def export_current_prompt(self, character: CharacterInfo, character_dir: Path):
        """Экспортировать текущий промпт персонажа"""
        prompt_file = character_dir / "current_prompt.txt"

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(f"# ТЕКУЩИЙ ПРОМПТ ПЕРСОНАЖА: {character.name}\n")
            f.write(f"# Экспорт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(character.system_prompt)

        print(f"  📄 Сохранен текущий промпт: current_prompt.txt")

    def export_statistics(self, character: CharacterInfo, dialogues: List[UserDialogue], character_dir: Path):
        """Экспортировать статистику по диалогам"""

        total_messages = sum(len(d.messages) for d in dialogues)
        message_lengths = []
        user_message_counts = []

        for dialogue in dialogues:
            user_message_counts.append(len(dialogue.messages))
            for msg in dialogue.messages:
                message_lengths.append(len(msg.content))

        avg_message_length = sum(message_lengths) / len(message_lengths) if message_lengths else 0

        # Группируем по активности
        activity_groups = {
            "1-5 сообщений": 0,
            "6-20 сообщений": 0,
            "21-50 сообщений": 0,
            "51-100 сообщений": 0,
            "101+ сообщений": 0,
        }

        for count in user_message_counts:
            if count <= 5:
                activity_groups["1-5 сообщений"] += 1
            elif count <= 20:
                activity_groups["6-20 сообщений"] += 1
            elif count <= 50:
                activity_groups["21-50 сообщений"] += 1
            elif count <= 100:
                activity_groups["51-100 сообщений"] += 1
            else:
                activity_groups["101+ сообщений"] += 1

        # Топ активных пользователей
        top_users = sorted(
            [(d.user_id, len(d.messages), d.first_message_date, d.last_message_date)
             for d in dialogues],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Сохраняем в читаемом формате
        stats_file = character_dir / "statistics.txt"

        with open(stats_file, 'w', encoding='utf-8') as f:
            f.write(f"📊 СТАТИСТИКА ПО ДИАЛОГАМ: {character.name}\n")
            f.write("=" * 60 + "\n\n")

            f.write("📈 ОСНОВНЫЕ МЕТРИКИ:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Всего пользователей: {len(dialogues)}\n")
            f.write(f"Всего сообщений: {total_messages}\n")
            f.write(f"Среднее сообщений на пользователя: {total_messages / len(dialogues):.1f}\n")
            f.write(f"Средняя длина сообщения: {avg_message_length:.0f} символов\n\n")

            f.write("📅 ПЕРИОД АКТИВНОСТИ:\n")
            f.write("-" * 40 + "\n")
            if dialogues:
                first_date = min(d.first_message_date for d in dialogues)
                last_date = max(d.last_message_date for d in dialogues)
                days_active = (last_date - first_date).days if last_date > first_date else 0
                f.write(f"Первое сообщение: {first_date}\n")
                f.write(f"Последнее сообщение: {last_date}\n")
                f.write(f"Период активности: {days_active} дней\n\n")

            f.write("👥 РАСПРЕДЕЛЕНИЕ ПО АКТИВНОСТИ:\n")
            f.write("-" * 40 + "\n")
            for group, count in activity_groups.items():
                if count > 0:
                    percentage = (count / len(dialogues)) * 100
                    f.write(f"{group:20} - {count:3} пользователей ({percentage:5.1f}%)\n")
            f.write("\n")

            f.write("🏆 ТОП-10 САМЫХ АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:\n")
            f.write("-" * 40 + "\n")
            for i, (user_id, msg_count, first_date, last_date) in enumerate(top_users, 1):
                duration_days = (last_date - first_date).days if last_date > first_date else 0
                f.write(f"{i:2}. ID {user_id:10} - {msg_count:4} сообщений за {duration_days:3} дней\n")

            f.write(f"\n📁 ФАЙЛЫ С ДИАЛОГАМИ:\n")
            f.write("-" * 40 + "\n")
            for i in range(len(dialogues)):
                f.write(f"dialogue_{i + 1:03d}_user_{dialogues[i].user_id}.txt\n")

        # Также сохраняем в JSON для машинного чтения
        json_stats = {
            "character_name": character.name,
            "total_users": len(dialogues),
            "total_messages": total_messages,
            "avg_messages_per_user": total_messages / len(dialogues) if dialogues else 0,
            "avg_message_length": avg_message_length,
            "activity_groups": activity_groups,
            "top_users": [
                {
                    "user_id": user_id,
                    "message_count": msg_count,
                    "first_message": first_date.isoformat(),
                    "last_message": last_date.isoformat()
                }
                for user_id, msg_count, first_date, last_date in top_users
            ],
            "export_date": datetime.now().isoformat()
        }

        json_file = character_dir / "statistics.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_stats, f, ensure_ascii=False, indent=2)

        print(f"  📈 Сохранена статистика: statistics.txt")

    def export_conversations(self, all_conversations: Dict[int, Dict]):
        """Основной метод экспорта всех диалогов"""

        print("\n" + "=" * 60)
        print("🚀 НАЧАЛО ЭКСПОРТА ДИАЛОГОВ")
        print("=" * 60)

        total_dialogues = sum(data['total_dialogues'] for data in all_conversations.values())
        total_messages = sum(data['total_messages'] for data in all_conversations.values())

        print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
        print(f"   Персонажей: {len(all_conversations)}")
        print(f"   Диалогов: {total_dialogues}")
        print(f"   Сообщений: {total_messages}")

        # Сортируем персонажей по количеству диалогов
        sorted_characters = sorted(
            all_conversations.items(),
            key=lambda x: x[1]['total_dialogues'],
            reverse=True
        )

        # Экспорт для каждого персонажа
        for character_id, character_data in sorted_characters:
            character = character_data['character']
            dialogues = character_data['dialogues']

            print(f"\n🎭 ПЕРСОНАЖ: {character.name}")
            print(f"   ID: {character_id}")
            print(f"   Диалогов: {len(dialogues)}")
            print(f"   Сообщений: {sum(len(d.messages) for d in dialogues)}")

            if not dialogues:
                print("   ⚠️ Нет диалогов для экспорта")
                continue

            # Создаем папку для персонажа
            safe_name = "".join(c for c in character.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            character_dir = self.output_dir / safe_name
            character_dir.mkdir(exist_ok=True)

            print(f"  📁 Создана папка: {character_dir.name}")

            # 1. Экспортируем текущий промпт
            self.export_current_prompt(character, character_dir)

            # 2. Создаем главный файл задачи
            dialogue_files = self.create_task_file(character, dialogues, character_dir)

            # 3. Экспортируем каждый диалог в отдельный файл
            print(f"  📄 Экспорт диалогов:")
            for i, dialogue in enumerate(dialogues, 1):
                filename = self.export_dialogue_file(character, dialogue, i, character_dir)
                if i <= 5 or i == len(dialogues):
                    print(f"    → {filename} ({len(dialogue.messages)} сообщений)")
                elif i == 6:
                    print(f"    ... и еще {len(dialogues) - 5} файлов")

            # 4. Экспортируем статистику
            self.export_statistics(character, dialogues, character_dir)

            # 5. Создаем инструкцию по использованию
            self.create_usage_guide(character, len(dialogues), character_dir)

        # Создаем общий отчет
        self.create_global_report(all_conversations)

        print(f"\n" + "=" * 60)
        print("✅ ЭКСПОРТ УСПЕШНО ЗАВЕРШЕН!")
        print("=" * 60)
        print(f"\n📁 Все файлы сохранены в: {self.output_dir.absolute()}")
        print("\n🎯 КАК ИСПОЛЬЗОВАТЬ:")
        print("1. Выберите папку с нужным персонажем")
        print("2. Прочитайте файл TASK.txt - это главная задача для AI")
        print("3. Передайте AI:")
        print("   - Файл TASK.txt (инструкция)")
        print("   - Файл current_prompt.txt (текущий промпт)")
        print("   - Все файлы dialogue_*.txt (диалоги)")
        print("4. Получите анализ и улучшения промпта")
        print("\n💡 СОВЕТ: Используйте Claude (100K контекст) или GPT-4 с загрузкой файлов")

    def create_usage_guide(self, character: CharacterInfo, num_dialogues: int, character_dir: Path):
        """Создать инструкцию по использованию файлов"""
        guide_content = f"""# 📖 ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ ФАЙЛОВ

        ## 🎯 ЦЕЛЬ ЭКСПОРТА
        Эти файлы созданы для анализа диалогов пользователей с персонажем "{character.name}" 
        и последующего улучшения его промпта.

        ## 📁 СОДЕРЖАНИЕ ПАПКИ

        ### ОСНОВНЫЕ ФАЙЛЫ:
        1. **`TASK.txt`** - Главная задача для AI-аналитика
        2. **`current_prompt.txt`** - Текущий промпт персонажа
        3. **`statistics.txt`** - Статистика по всем диалогам
        4. **`statistics.json`** - Статистика в JSON формате
        5. **`USAGE_GUIDE.txt`** - Этот файл

        ### ФАЙЛЫ С ДИАЛОГАМИ:
        Всего: {num_dialogues} файлов

        Имена файлов: `dialogue_001_user_XXXXX.txt` ... `dialogue_{num_dialogues:03d}_user_XXXXX.txt`

        Каждый файл содержит полный диалог одного пользователя с персонажем.

        ## 🚀 КАК ПЕРЕДАТЬ AI ДЛЯ АНАЛИЗА

        ### ВАРИАНТ 1: Claude (Anthropic) - РЕКОМЕНДУЕМЫЙ
        Claude поддерживает большие контексты (до 100K токенов) и хорошо работает с файлами.

        **Как использовать:**
        1. Загрузите ВСЕ файлы в Claude
        2. Скажите: "Прочитай файл TASK.txt и выполни задание"
        3. Claude прочитает все файлы и даст развернутый анализ

        ### ВАРИАНТ 2: ChatGPT/GPT-4 с загрузкой файлов
        **Как использовать:**
        1. Загрузите файлы по одному или архивом
        2. Начните с: "Прочитай файл TASK.txt - это инструкция"
        3. Затем: "Вот диалоги пользователей: [перечисли файлы]"
        4. Попросите проанализировать и улучшить промпт

        ### ВАРИАНТ 3: Локальная модель (Ollama, Llama)
        **Как использовать:**
        1. Объедините содержимое ключевых файлов:
        cat TASK.txt current_prompt.txt statistics.txt > combined.txt
        2. Добавьте несколько примеров диалогов
        3. Передайте объединенный файл модели

        ## 📊 ЧТО АНАЛИЗИРОВАТЬ

        ### ОБЯЗАТЕЛЬНО:
        1. **Прочитать `TASK.txt`** - полная инструкция
        2. **Прочитать `current_prompt.txt`** - текущий промпт
        3. **Прочитать ВСЕ диалоги** - каждый файл содержит уникальный опыт

        ### РЕКОМЕНДУЕМАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ:
        1. Начните с `TASK.txt` - поймите задачу
        2. Прочитайте `current_prompt.txt` - поймите текущее состояние
        3. Изучите `statistics.txt` - общая картина
        4. Читайте диалоги по порядку или выборочно
        5. Сделайте выводы и предложите улучшения

        ## 💡 СОВЕТЫ ПО АНАЛИЗУ

        1. **Обращайте внимание на паттерны** - что повторяется в диалогах
        2. **Ищите "боли" пользователей** - что не получается у персонажа
        3. **Отмечайте успехи** - что хорошо работает
        4. **Учитывайте контекст** - Telegram, неформальное общение
        5. **Будьте конкретны** - предлагайте конкретные формулировки для промпта

        ## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

        - **НЕ пропускайте диалоги** - каждый файл содержит ценный опыт
        - **НЕ меняйте структуру файлов** - она оптимизирована для анализа
        - **НЕ удаляйте метаданные** - даты, ID пользователей важны для контекста
        - **ДА, нужно читать всё** - даже короткие диалоги могут содержать инсайты

        ## 🎭 О ПЕРСОНАЖЕ

        **Имя:** {character.name}
        **Описание:** {character.description[:200]}...

        ## 📅 ИНФОРМАЦИЯ ОБ ЭКСПОРТЕ
        - Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        - Всего диалогов: {num_dialogues}
        - Папка: {character_dir.name}

        Удачи в анализе! Ваша работа сделает персонажа лучше для тысяч пользователей.
        """

        guide_file = character_dir / "USAGE_GUIDE.txt"
        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(guide_content)

    def create_global_report(self, all_conversations: Dict[int, Dict]):
        """Создать общий отчет по всем персонажам"""

        report_file = self.output_dir / "GLOBAL_REPORT.txt"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# 📊 ГЛОБАЛЬНЫЙ ОТЧЕТ ПО ЭКСПОРТУ ДИАЛОГОВ\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Всего персонажей: {len(all_conversations)}\n\n")

            f.write("## 📈 СТАТИСТИКА ПО ПЕРСОНАЖАМ:\n")
            f.write("-" * 40 + "\n")

            # Сортируем по количеству диалогов
            sorted_data = sorted(
                [(data['character'].name, data['total_dialogues'], data['total_messages'])
                 for data in all_conversations.values()],
                key=lambda x: x[1],
                reverse=True
            )

            for name, dialogues, messages in sorted_data:
                avg = messages / dialogues if dialogues > 0 else 0
                f.write(f"\n🎭 {name}:\n")
                f.write(f"  • Диалогов: {dialogues}\n")
                f.write(f"  • Сообщений: {messages:,}\n")
                f.write(f"  • Среднее на диалог: {avg:.1f}\n")

            total_dialogues = sum(data['total_dialogues'] for data in all_conversations.values())
            total_messages = sum(data['total_messages'] for data in all_conversations.values())

            f.write(f"\n\n## 📊 ИТОГО:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Всего диалогов: {total_dialogues:,}\n")
            f.write(f"Всего сообщений: {total_messages:,}\n")
            f.write(f"Среднее сообщений на диалог: {total_messages / total_dialogues:.1f}\n\n")

            f.write("## 🚀 КАК ИСПОЛЬЗОВАТЬ:\n")
            f.write("-" * 40 + "\n")
            f.write("1. Выберите папку с нужным персонажем\n")
            f.write("2. В каждой папке есть:\n")
            f.write("   • TASK.txt - главная задача для AI\n")
            f.write("   • current_prompt.txt - текущий промпт\n")
            f.write("   • statistics.txt - статистика\n")
            f.write("   • dialogue_*.txt - все диалоги\n")
            f.write("   • USAGE_GUIDE.txt - инструкция\n")
            f.write("\n3. Передайте AI файлы в таком порядке:\n")
            f.write("   1. TASK.txt (инструкция)\n")
            f.write("   2. current_prompt.txt (что улучшать)\n")
            f.write("   3. Все файлы dialogue_*.txt (данные для анализа)\n")
            f.write("\n4. Получите анализ и улучшите промпт!\n")

            f.write("\n## 💡 РЕКОМЕНДАЦИИ:\n")
            f.write("-" * 40 + "\n")
            f.write("• Используйте Claude (100K контекст) для лучших результатов\n")
            f.write("• Анализируйте по одному персонажу за раз\n")
            f.write("• Сохраняйте оригинальные промпты для сравнения\n")
            f.write("• Тестируйте улучшения на реальных пользователях\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("✅ ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО!\n")
            f.write("=" * 60 + "\n")

def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(
        description='Экспорт диалогов для анализа промптов с умной структурой',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Примеры использования:
    python export_conversations_for_analysis.py
    python export_conversations_for_analysis.py --output-dir ./analysis

    Структура экспорта:
    output_dir/
     ├── Character_Name/
     │   ├── TASK.txt                    # Главная задача для AI
     │   ├── current_prompt.txt          # Текущий промпт
     │   ├── statistics.txt              # Статистика
     │   ├── dialogue_001_user_12345.txt # Диалог 1
     │   ├── dialogue_002_user_67890.txt # Диалог 2
     │   └── ...                         # Все диалоги
     ├── Another_Character/
     │   └── ...                         # Аналогичная структура
     └── GLOBAL_REPORT.txt               # Общий отчет
         """
    )

    parser.add_argument('--output-dir', type=str, default='./conversation_analysis',
                        help='Директория для сохранения результатов')
    parser.add_argument('--db-host', type=str, default='localhost',
                        help='Хост базы данных')
    parser.add_argument('--db-port', type=int, default=15432,
                        help='Порт базы данных')
    parser.add_argument('--db-name', type=str, default='ai-friend',
                        help='Имя базы данных')
    parser.add_argument('--db-user', type=str, default='temporal',
                        help='Пользователь базы данных')
    parser.add_argument('--db-password', type=str, default='temporal',
                        help='Пароль базы данных')

    args = parser.parse_args()

    print(f"🚀 ЗАПУСК УМНОГО ЭКСПОРТА ДИАЛОГОВ...")
    print(f"📁 Выходная директория: {args.output_dir}")
    print(f"🗄️  База данных: {args.db_name}@{args.db_host}:{args.db_port}")
    print("=" * 60)

    try:
        # Конфигурация базы данных
        db_config = DatabaseConfig(
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password
        )

        # Инициализация экспортера
        exporter = ConversationExporter(db_config)

        if not exporter.connect():
            sys.exit(1)

        # Получение всех диалогов
        print("\n📥 ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ...")
        all_conversations = exporter.get_all_conversations()

        # Инициализация анализатора
        analyzer = DialogueExporter(args.output_dir)

        # Экспорт данных
        analyzer.export_conversations(all_conversations)

        # Закрытие соединения
        exporter.disconnect()

    except KeyboardInterrupt:
        print("\n⚠️ Экспорт прерван пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()