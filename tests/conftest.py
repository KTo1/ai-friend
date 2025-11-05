# tests/conftest.py
import pytest
import os
import sys

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Глобальные фикстуры можно добавить здесь
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Настройка тестового окружения для всех тестов"""
    # Устанавливаем тестовые переменные окружения
    os.environ['AI_PROVIDER'] = 'test'
    os.environ['ENABLE_METRICS'] = 'false'
    os.environ['LOG_LEVEL'] = 'ERROR'

    yield

    # Очистка после тестов
    if 'TEST_DB' in os.environ:
        if os.path.exists(os.environ['TEST_DB']):
            os.remove(os.environ['TEST_DB'])