from typing import List, Dict
from datetime import datetime
from infrastructure.database.database import Database


class ConversationRepository:
    def __init__(self, database: Database):
        self.db = database

    def save_message(self, user_id: int, character_id: int, role: str, content: str):
        """Сохранить сообщение с учетом лимита контекста"""
        self.db.execute_query('''
            INSERT INTO conversation_context (user_id, character_id, role, content)
            VALUES (%s, %s, %s, %s)
        ''', (user_id, character_id, role, content))

    def get_conversation_context(self, user_id: int, character_id: int,
                                 max_context_messages: int = 10) -> List[Dict]:
        """Получить контекст разговора с учетом лимита"""
        results = self.db.fetch_all('''
            SELECT role, content 
            FROM conversation_context 
            WHERE user_id = %s AND character_id = %s AND deleted_at is NULL
            ORDER BY timestamp ASC 
            LIMIT %s
        ''', (user_id, character_id, max_context_messages))

        return [{'role': row['role'], 'content': row['content']} for row in results]

    def get_conversation_count(self, user_id: int, character_id: int) -> int:
        """Получить контекст разговора с учетом лимита"""
        result = self.db.fetch_one('''
            SELECT count(*) 
            FROM conversation_context 
            WHERE user_id = %s AND character_id = %s AND deleted_at is NULL
        ''', (user_id, character_id))

        if result:
            return result['count']

        return 0

    def clear_conversation(self, user_id: int, character_id: int):
        """Очистить историю разговора"""
        #self.db.execute_query('DELETE FROM conversation_context WHERE user_id = %s AND character_id = %s', (user_id, character_id))
        self.db.execute_query('UPDATE conversation_context SET deleted_at = %s WHERE user_id = %s AND character_id = %s',
                              (datetime.utcnow(), user_id, character_id))
