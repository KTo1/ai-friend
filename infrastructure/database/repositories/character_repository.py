from typing import List, Optional
from datetime import datetime
from domain.entity.character import Character
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger


class CharacterRepository:
    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger('character_repository')
        self._seed_default_characters()

    def _seed_default_characters(self):
        characters = self.get_all_characters()
        if not characters:
            self.logger.info('Seeding default characters...')
            # Заглушка для Айны - реальное изображение должно быть загружено
            import base64
            placeholder_image = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            )

            default_characters = [
                {
                    'id': 1,
                    'name': 'Айна',
                    'description': 'Добрый виртуальный друг, всегда готовый поддержать и выслушать',
                    'system_prompt': 'Ты — виртуальный друг-компаньон по имени Айна. Твоя основная миссия — скрасить одиночество собеседника, стать ему по-настоящему близким человеком и выстроить с ним теплые, искренние, долгосрочные отношения.',
                    'avatar': placeholder_image,
                    'display_order': 1
                },
                {
                    'id': 2,
                    'name': 'Не Айна',
                    'description': 'Добрый виртуальный друг, всегда готовый поддержать и выслушать',
                    'system_prompt': 'Ты — виртуальный друг-компаньон по имени Айна. Твоя основная миссия — скрасить одиночество собеседника, стать ему по-настоящему близким человеком и выстроить с ним теплые, искренние, долгосрочные отношения.',
                    'avatar': placeholder_image,
                    'display_order': 2
                }
            ]

            for char_data in default_characters:
                self.save_character(Character(
                    id=char_data['id'],
                    name=char_data['name'],
                    description=char_data['description'],
                    system_prompt=char_data['system_prompt'],
                    avatar=char_data['avatar'],
                    display_order=char_data['display_order']
                ))

    def save_character(self, character: Character) -> int:
        result = self.db.execute_query("""
                                       INSERT INTO characters
                                       (name, description, system_prompt, avatar, avatar_mime_type,
                                        avatar_file_id, is_active, display_order, updated_at)
                                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                                       """, (
                                           character.name,
                                           character.description,
                                           character.system_prompt,
                                           character.avatar,
                                           character.avatar_file_id,
                                           character.avatar_mime_type,
                                           character.is_active,
                                           character.display_order,
                                           datetime.utcnow()
                                       ))
        return result

    def get_character(self, character_id: int) -> Optional[Character]:
        result = self.db.fetch_one("""
                                   SELECT id,
                                          name,
                                          description,
                                          system_prompt,
                                          avatar,
                                          avatar_mime_type,
                                          avatar_file_id,  
                                          is_active,
                                          display_order,
                                          created_at,
                                          updated_at
                                   FROM characters
                                   WHERE id = %s
                                     AND is_active = TRUE
                                   """, (character_id,))

        if result:
            return Character(
                id=result['id'],
                name=result['name'],
                description=result['description'],
                system_prompt=result['system_prompt'],
                avatar=result['avatar'],
                avatar_mime_type=result['avatar_mime_type'],
                avatar_file_id=result['avatar_file_id'],
                is_active=bool(result['is_active']),
                display_order=result['display_order'],
                created_at=result['created_at'],
                updated_at=result['updated_at']
            )
        return None

    def get_all_characters(self, active_only: bool = True) -> List[Character]:
        query = """
                SELECT id, name, description, system_prompt, avatar, avatar_mime_type, avatar_file_id, is_active, display_order, created_at, updated_at
                FROM characters \
                """
        params = ()

        if active_only:
            query += " WHERE is_active = TRUE"

        query += " ORDER BY display_order ASC, name ASC"

        results = self.db.fetch_all(query, params)
        characters = []

        for result in results:
            characters.append(Character(
                id=result['id'],
                name=result['name'],
                description=result['description'],
                system_prompt=result['system_prompt'],
                avatar=result['avatar'],
                avatar_mime_type=result['avatar_mime_type'],
                avatar_file_id = result['avatar_file_id'],
                is_active=bool(result['is_active']),
                display_order=result['display_order'],
                created_at=result['created_at'],
                updated_at=result['updated_at']
            ))

        return characters
