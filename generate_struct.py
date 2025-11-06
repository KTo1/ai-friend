import os
import pathlib


def get_project_structure(root_dir=".", output_file="project_structure.txt", exclude_dirs=None):
    """
    Создает текстовый файл со структурой проекта и листингом модулей

    Args:
        root_dir (str): Корневая директория проекта
        output_file (str): Имя выходного файла
        exclude_dirs (list): Список директорий для исключения
    """

    if exclude_dirs is None:
        exclude_dirs = ['.git', '__pycache__', '.vscode', '.idea', 'venv', 'env', 'node_modules']

    root_path = pathlib.Path(root_dir)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("📁 СТРУКТУРА ПРОЕКТА И ЛИСТИНГ МОДУЛЕЙ\n")
        f.write("=" * 60 + "\n\n")

        # Собираем структуру
        python_files = []

        for file_path in root_path.rglob('*'):
            if any(exclude in str(file_path) for exclude in exclude_dirs):
                continue

            relative_path = file_path.relative_to(root_path)

            if file_path.is_file():
                if file_path.suffix in ['.py', '.txt', '.md', '.yml', '.yaml', '.json', '.env']:
                    # Записываем файл
                    indent = "  " * (len(relative_path.parts) - 1)
                    icon = "📄" if file_path.suffix == '.py' else "📝"
                    f.write(f"{indent}{icon} {relative_path}\n")

                    if file_path.suffix == '.py':
                        python_files.append(file_path)
            else:
                # Записываем директорию
                indent = "  " * (len(relative_path.parts) - 1)
                f.write(f"{indent}📁 {relative_path}/\n")

        # Добавляем листинг Python модулей
        f.write("\n" + "=" * 60 + "\n")
        f.write("🐍 ЛИСТИНГ PYTHON МОДУЛЕЙ\n")
        f.write("=" * 60 + "\n\n")

        for py_file in sorted(python_files):
            f.write(f"\n{'━' * 80}\n")
            f.write(f"📄 {py_file.relative_to(root_path)}\n")
            f.write(f"{'━' * 80}\n")

            try:
                with open(py_file, 'r', encoding='utf-8') as pf:
                    content = pf.read()
                    if content.strip():  # Если файл не пустой
                        f.write(content + "\n")
                    else:
                        f.write("# (пустой файл)\n")
            except Exception as e:
                f.write(f"# Ошибка чтения файла: {e}\n")

    print(f"Структура проекта сохранена в: {output_file}")
    print(f"Найдено Python файлов: {len(python_files)}")


def get_compact_structure(root_dir=".", output_file="project_compact.txt"):
    """
    Компактная версия только со структурой (без содержимого файлов)
    """
    exclude_dirs = ['.git', '__pycache__', '.vscode', '.idea', 'venv', 'env', 'node_modules']
    root_path = pathlib.Path(root_dir)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("📁 КОМПАКТНАЯ СТРУКТУРА ПРОЕКТА\n")
        f.write("=" * 50 + "\n\n")

        python_files = []

        for file_path in sorted(root_path.rglob('*')):
            if any(exclude in str(file_path) for exclude in exclude_dirs):
                continue

            relative_path = file_path.relative_to(root_path)

            if file_path.is_file():
                if file_path.suffix in ['.py', '.txt', '.md', '.yml', '.yaml', '.json']:
                    indent = "    " * (len(relative_path.parts) - 1)
                    icon = "🐍" if file_path.suffix == '.py' else "📄"
                    f.write(f"{indent}{icon} {relative_path}\n")

                    if file_path.suffix == '.py':
                        python_files.append(relative_path)
            else:
                indent = "    " * (len(relative_path.parts) - 1)
                f.write(f"{indent}📁 {relative_path}/\n")

        # Список всех Python модулей
        f.write(f"\n📊 Всего Python модулей: {len(python_files)}\n")
        for py_file in sorted(python_files):
            f.write(f"   • {py_file}\n")

    print(f"✅ Компактная структура сохранена в: {output_file}")


if __name__ == "__main__":
    # Создаем полную версию с кодом
    get_project_structure(".", "project_structure_full.txt")

    # Создаем компактную версию
    get_compact_structure(".", "project_structure_compact.txt")

    print("\n🎯 Теперь вы можете отправить мне:")
    print("   • project_structure_compact.txt - для общей структуры")
    print("   • project_structure_full.txt - если нужен полный код")
    print("\n💡 Рекомендую начать с компактной версии!")