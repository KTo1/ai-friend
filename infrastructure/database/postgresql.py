import logging
import psycopg2
import psycopg2.extras
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from infrastructure.monitoring.logging import StructuredLogger

logger = StructuredLogger("postgresql")


class PostgreSQLDatabase:
    def __init__(self, db_config):
        self.db_config = db_config
        self.logger = StructuredLogger("postgresql")
        self.init_db()

    def get_connection(self):
        """Получить соединение с базой данных"""
        try:
            conn = psycopg2.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                database=self.db_config.name,
                user=self.db_config.user,
                password=self.db_config.password,
                cursor_factory=psycopg2.extras.DictCursor
            )
            return conn
        except Exception as e:
            self.logger.error(f"Database connection error: {e}")
            raise

    @contextmanager
    def get_cursor(self):
        """Контекстный менеджер для работы с курсором"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with self.get_cursor() as cursor:
                # Включение расширения vector для векторных операций
                cursor.execute(''' CREATE EXTENSION IF NOT EXISTS vector; ''')

                # Таблица для RAG памяти (уже создается в коде, но можно добавить и здесь)
                cursor.execute(''' 
                    CREATE TABLE IF NOT EXISTS user_rag_memories (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    memory_type VARCHAR(40) NOT NULL,
                    content TEXT NOT NULL,
                    source_message TEXT,
                    importance_score FLOAT DEFAULT 0.5,
                    embedding vector(384), -- Используем расширение vector
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}',
                    
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    );
                ''')

                #  Индексы для эффективного поиска
                cursor.execute(''' CREATE INDEX IF NOT EXISTS idx_rag_memories_user_id ON user_rag_memories(user_id);''')
                cursor.execute(''' CREATE INDEX IF NOT EXISTS idx_rag_memories_importance ON user_rag_memories(importance_score DESC); ''')
                cursor.execute(''' CREATE INDEX IF NOT EXISTS idx_rag_memories_type ON user_rag_memories(memory_type); ''')
                cursor.execute(''' CREATE INDEX IF NOT EXISTS idx_rag_memories_embedding ON user_rag_memories USING ivfflat (embedding vector_cosine_ops); ''')

                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_admin BOOLEAN DEFAULT FALSE,
                        is_blocked BOOLEAN DEFAULT FALSE,
                        blocked_reason TEXT,
                        blocked_at TIMESTAMP,
                        blocked_by BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица профилей пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        name TEXT,
                        age INTEGER,
                        interests TEXT,
                        mood TEXT,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица контекста разговоров
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversation_context (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица активности пользователей для проактивных сообщений
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_activity (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        last_message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_proactive_time TIMESTAMP,
                        message_count INTEGER DEFAULT 0,
                        timezone_offset INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица лимитов сообщений
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_message_limits (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        config JSONB NOT NULL,
                        total_messages_processed INTEGER DEFAULT 0,
                        total_characters_processed INTEGER DEFAULT 0,
                        average_message_length REAL DEFAULT 0.0,
                        rejected_messages_count INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица рейт-лимитов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_rate_limits (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        message_counts JSONB NOT NULL,
                        last_reset JSONB NOT NULL,
                        config JSONB NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица тарифных планов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tariff_plans (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        price REAL DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_default BOOLEAN DEFAULT FALSE,
                        rate_limits JSONB NOT NULL,
                        message_limits JSONB NOT NULL,
                        features JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица пользовательских тарифов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_tariffs (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        tariff_plan_id INTEGER REFERENCES tariff_plans(id),
                        activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')

                # Создаем индексы для улучшения производительности
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversation_context_user_id 
                    ON conversation_context(user_id, timestamp DESC)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_users_last_seen 
                    ON users(last_seen DESC)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_users_is_admin 
                    ON users(is_admin) WHERE is_admin = TRUE
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_users_is_blocked 
                    ON users(is_blocked) WHERE is_blocked = TRUE
                ''')

            self.logger.info("PostgreSQL database initialized successfully")

        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise

    def execute_query(self, query: str, params: tuple = ()) -> Any:
        """Выполнить запрос к базе данных"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    return cursor.rowcount
                return cursor
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            raise

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Получить одну запись"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Fetch one error: {e}")
            return None

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        """Получить все записи"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Fetch all error: {e}")
            return []

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Выполнить массовую вставку/обновление"""
        try:
            with self.get_cursor() as cursor:
                cursor.executemany(query, params_list)
                return cursor.rowcount
        except Exception as e:
            self.logger.error(f"Execute many error: {e}")
            raise