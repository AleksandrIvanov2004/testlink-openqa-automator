-- =================================================================
-- Инициализация БД для TestLink-OpenQA Automator
-- Выполняется ТОЛЬКО при первом создании БД
-- =================================================================

-- Включаем расширения PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Настройки для лучшей производительности
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET maintenance_work_mem = '128MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;

-- Выбираем лучшую конфигурацию text search для смешанного контента (рус+eng)
ALTER DATABASE testauto SET default_text_search_config = 'pg_catalog.russian';

-- Создаем роли (если нужно)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'testauto_user') THEN
        CREATE ROLE testauto_user WITH LOGIN PASSWORD 'SecurePass2026!';
    END IF;

    GRANT ALL PRIVILEGES ON DATABASE testauto TO testauto_user;
END $$;

-- =================================================================
-- Логирование для отладки (удалить в production)
-- =================================================================
\echo '✅ Инициализация БД завершена успешно!'
\q
