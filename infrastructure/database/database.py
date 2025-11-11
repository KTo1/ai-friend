import os
from config.settings import config
from infrastructure.database.postgresql import PostgreSQLDatabase


class Database:
    def __init__(self):
        self.db = PostgreSQLDatabase(config.database)
        self.logger = self.db.logger

    def __getattr__(self, name):
        """Делегируем методы PostgreSQLDatabase"""
        return getattr(self.db, name)

    def init_db(self):
        """Инициализация базы данных (для обратной совместимости)"""
        return self.db.init_db()

    def execute_query(self, query: str, params: tuple = ()):
        """Выполнить запрос к базе данных"""
        return self.db.execute_query(query, params)

    def fetch_one(self, query: str, params: tuple = ()):
        """Получить одну запись"""
        return self.db.fetch_one(query, params)

    def fetch_all(self, query: str, params: tuple = ()):
        """Получить все записи"""
        return self.db.fetch_all(query, params)