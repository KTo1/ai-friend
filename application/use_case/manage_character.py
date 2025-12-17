from typing import List, Tuple, Optional, Dict, Any
from domain.entity.character import Character
from domain.entity.user import User
from infrastructure.database.repositories.character_repository import CharacterRepository
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageCharacterUseCase:
    def __init__(self, character_repository: CharacterRepository, user_repository: UserRepository):
        self.character_repo = character_repository
        self.user_repo = user_repository
        self.logger = StructuredLogger('manage_character_uc')

    @trace_span('usecase.get_all_characters', attributes={'component': 'application'})
    def get_all_characters(self) -> List[Character]:
        return self.character_repo.get_all_characters(active_only=True)

    @trace_span('usecase.get_user_character', attributes={'component': 'application'})
    def get_user_character(self, user_id: int) -> Optional[Character]:
        user = self.user_repo.get_user(user_id)
        if not user or not user.current_character_id:
            return None
        return self.character_repo.get_character(user.current_character_id)

    @trace_span('usecase.set_user_character', attributes={'component': 'application'})
    def set_user_character(self, user_id: int, character_id: int) -> Tuple[bool, str]:
        try:
            character = self.character_repo.get_character(character_id)
            if not character:
                return False, f'❌ Персонаж с ID {character_id} не найден'

            user = self.user_repo.get_user(user_id)
            if not user:
                return False, f'❌ Пользователь с ID {user_id} не найден'

            user.set_character(character_id)
            self.user_repo.save_user(user)

            self.logger.info(f'User {user_id} selected character {character_id} ({character.name})')
            return True, f'✅ Вы выбрали персонажа: {character.name}\n\n{character.description}'
        except Exception as e:
            self.logger.error(f'Error setting character for user {user_id}: {e}')
            return False, f'❌ Ошибка при выборе персонажа: {str(e)}'

    @trace_span('usecase.get_character_info', attributes={'component': 'application'})
    def get_character_info(self, character_id: int) -> Optional[Dict[str, Any]]:
        character = self.character_repo.get_character(character_id)
        if not character:
            return None

        return {
            'id': character.id,
            'name': character.name,
            'description': character.description,
            'prompt_preview': character.system_prompt[:100] + '...' if len(
                character.system_prompt) > 100 else character.system_prompt,
            'avatar_mime_type': character.avatar_mime_type,
            'avatar_size': len(character.avatar)
        }