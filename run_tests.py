# run_tests.py
# !/usr/bin/env python3
"""
Скрипт для запуска всех тестов
"""
import pytest
import sys
import os

if __name__ == "__main__":
    # Добавляем корневую директорию в путь
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Запускаем pytest
    exit_code = pytest.main([
        "tests/",
        "-v",  # Подробный вывод
        "--tb=short",  # Короткий traceback
        "-x"  # Остановить при первой ошибке
    ])

    sys.exit(exit_code)