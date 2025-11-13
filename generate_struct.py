import os
import pathlib


def split_file_content(content, lines_per_file=5):
    """
    Разбивает содержимое на части по указанному количеству строк

    Args:
        content (str): Исходное содержимое
        lines_per_file (int): Количество строк в каждом файле

    Returns:
        list: Список строк, разбитый на части
    """
    lines = content.split('\n')
    chunks = []

    for i in range(0, len(lines), lines_per_file):
        chunk = lines[i:i + lines_per_file]
        chunks.append('\n'.join(chunk))

    return chunks


def get_project_structure(root_dir=".", output_file="project_structure.txt", exclude_dirs=None, lines_per_file=5):
    """
    Создает текстовый файл со структурой проекта и листингом модулей

    Args:
        root_dir (str): Корневая директория проекта
        output_file (str): Базовое имя выходного файла
        exclude_dirs (list): Список директорий для исключения
        lines_per_file (int): Количество строк в каждом файле
    """

    if exclude_dirs is None:
        exclude_dirs = ['.git', '__pycache__', '.vscode', '.idea', 'venv', 'env', 'node_modules', '.github']

    root_path = pathlib.Path(root_dir)
    supported_suffixes = ['.py', '.md', '.yml', '.yaml', '.json', '.env']

    full_content = ""

    # Собираем полное содержимое
    full_content += "=" * 60 + "\n"
    full_content += "📁 СТРУКТУРА ПРОЕКТА И ЛИСТИНГ МОДУЛЕЙ\n"
    full_content += "=" * 60 + "\n\n"

    files_to_list = []

    # Сначала записываем структуру
    for file_path in root_path.rglob('*'):
        if any(exclude in str(file_path) for exclude in exclude_dirs):
            continue

        # Игнорируем сам выходной файл
        if file_path.name.startswith(output_file.replace('.txt', '')):
            continue

        relative_path = file_path.relative_to(root_path)

        if file_path.is_file():
            if file_path.suffix in supported_suffixes:
                # Записываем файл в структуру
                indent = "  " * (len(relative_path.parts) - 1)
                icon = "🐍" if file_path.suffix == '.py' else "📝"
                full_content += f"{indent}{icon} {relative_path}\n"

                # Добавляем файл в список для последующего листинга содержимого
                files_to_list.append(file_path)
        else:
            # Записываем директорию
            indent = "  " * (len(relative_path.parts) - 1)
            full_content += f"{indent}📁 {relative_path}/\n"

    if not files_to_list:
        full_content += "\n(Нет поддерживаемых файлов для листинга в проекте)\n"

    # Добавляем листинг содержимого файлов
    full_content += "\n" + "=" * 60 + "\n"
    full_content += "📜 ЛИСТИНГ СОДЕРЖИМОГО ФАЙЛОВ\n"
    full_content += "=" * 60 + "\n\n"

    # Выводим содержимое всех собранных файлов
    for file_path in sorted(files_to_list):
        relative_path = file_path.relative_to(root_path)
        full_content += f"\n{'━' * 80}\n"
        full_content += f"📄 {relative_path}\n"
        full_content += f"{'━' * 80}\n"

        try:
            with open(file_path, 'r', encoding='utf-8') as pf:
                content = pf.read()
                if content.strip():
                    full_content += content + "\n"
                else:
                    full_content += "# (пустой файл)\n"
        except Exception as e:
            full_content += f"# Ошибка чтения файла: {e}\n"

    # Разбиваем содержимое на части
    chunks = split_file_content(full_content, lines_per_file)

    # Сохраняем каждый кусок в отдельный файл
    base_name = output_file.replace('.txt', '')
    file_count = len(chunks)

    for i, chunk in enumerate(chunks, 1):
        chunk_filename = f"{base_name}_part_{i:02d}_of_{file_count:02d}.txt"
        with open(chunk_filename, 'w', encoding='utf-8') as f:
            f.write(chunk)

    print(f"✅ Структура проекта сохранена в {file_count} файлов:")
    for i in range(1, file_count + 1):
        print(f"   📄 {base_name}_part_{i:02d}_of_{file_count:02d}.txt")
    print(f"📊 Найдено файлов для листинга: {len(files_to_list)}")
    print(f"📝 Строк в каждом файле: {lines_per_file}")


if __name__ == "__main__":
    lines_per_chunk = 6000 # Количество строк в каждом файле

    # Создаем полную версию с кодом
    get_project_structure(".", "project_structure_full.txt", lines_per_file=lines_per_chunk)

    print(f"\n🎯 Теперь вы можете отправить мне файлы частями по {lines_per_chunk} строк:")
    print("   • project_structure_full_part_XX_of_XX.txt - если нужен полный код")
    print("\n💡 Отправляйте файлы по одному или небольшими группами!")