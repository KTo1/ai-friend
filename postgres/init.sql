-- Создание расширения для UUID если нужно
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Дополнительные настройки производительности
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.track = 'all';