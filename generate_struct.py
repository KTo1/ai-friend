import pathlib
import ast


def strip_python_code(content):
    """
    Удаляет докстроки и комментарии из Python-кода

    Args:
        content (str): Исходный Python-код

    Returns:
        str: Очищенный Python-код
    """
    try:
        # Парсим AST для удаления докстрок
        tree = ast.parse(content)

        # Удаляем docstring из модуля
        if hasattr(tree, 'body') and tree.body:
            first_expr = tree.body[0]
            if isinstance(first_expr, ast.Expr) and isinstance(first_expr.value, ast.Str):
                tree.body = tree.body[1:]

        # Обходим все узлы AST и удаляем docstring из функций и классов
        for node in ast.walk(tree):
            # Для функций и методов
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
                    node.body = node.body[1:]
            # Для классов
            elif isinstance(node, ast.ClassDef):
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
                    node.body = node.body[1:]

        # Преобразуем обратно в код
        cleaned_content = ast.unparse(tree) if hasattr(ast, 'unparse') else ast.dump(tree)

        # Удаляем однострочные комментарии
        lines = cleaned_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Удаляем комментарии, но не удаляем пустые строки для сохранения структуры
            if '#' in line:
                # Разделяем строку по комментарию и берем только код до него
                code_part = line.split('#')[0]
                if code_part.strip():  # Если остался код, добавляем его
                    cleaned_lines.append(code_part.rstrip())
                else:
                    # Пустая строка вместо строки с комментарием
                    cleaned_lines.append('')
            else:
                cleaned_lines.append(line.rstrip())

        # Удаляем пустые строки в начале и конце файла
        cleaned_content = '\n'.join(cleaned_lines)
        cleaned_content = cleaned_content.strip()

        return cleaned_content

    except (SyntaxError, ValueError) as e:
        # Если не удалось распарсить, используем простой метод удаления комментариев
        print(f"  ⚠️  Внимание: не удалось обработать Python-файл через AST: {e}")

        # Простой метод удаления комментариев через регулярные выражения
        # Удаляем однострочные комментарии
        lines = content.split('\n')
        cleaned_lines = []
        in_multiline_comment = False
        multiline_comment_type = None  # ' или """

        for line in lines:
            stripped = line.strip()

            # Пропускаем пустые строки и строки, содержащие только комментарии
            if not stripped or stripped.startswith('#'):
                continue

            # Проверяем многострочные комментарии
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    # Однострочный многострочный комментарий - пропускаем
                    continue
                else:
                    # Начало многострочного комментария
                    in_multiline_comment = True
                    multiline_comment_type = stripped[:3]
                    continue

            if in_multiline_comment:
                if multiline_comment_type in line:
                    in_multiline_comment = False
                continue

            # Удаляем встроенные комментарии
            if '#' in line:
                code_part = line.split('#')[0]
                if code_part.strip():
                    cleaned_lines.append(code_part.rstrip())
            else:
                cleaned_lines.append(line.rstrip())

        return '\n'.join(cleaned_lines)


def get_project_structure(root_dir=".", output_file="project_structure.txt",
                          exclude_dirs=None, include_dirs=None, exclude_files=None,
                          strip_docstrings_and_comments=False):
    """
    Создает текстовый файл со структурой проекта и листингом модулей

    Args:
        root_dir (str): Корневая директория проекта
        output_file (str): Имя выходного файла
        exclude_dirs (list): Список директорий для исключения
        include_dirs (list): Список директорий для включения (если None - включаем все)
        exclude_files (list): Список файлов для исключения (можно указывать с путями или шаблонами)
        strip_docstrings_and_comments (bool): Если True, удаляет докстроки и комментарии из Python-файлов
    """

    if exclude_dirs is None:
        # Добавил .github, чтобы исключить стандартные CI/CD папки
        exclude_dirs = []

    if exclude_files is None:
        exclude_files = []

    if include_dirs is None:
        include_dirs = []  # Пустой список означает "включать всё"

    root_path = pathlib.Path(root_dir)

    # Определяем типы файлов, для которых будем выводить содержимое и отображать в структуре
    supported_suffixes = ['.py', '.md', '.yml', '.yaml', '.json', '.env', '.conf', '.dockerignore']

    # Файлы без расширения, которые нужно включить
    important_files_without_extension = ['Dockerfile', 'Makefile']

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("📁 СТРУКТУРА ПРОЕКТА И ЛИСТИНГ МОДУЛЕЙ\n")
        f.write("=" * 60 + "\n")

        # Добавляем информацию о фильтрах
        if include_dirs:
            f.write(f"ВКЛЮЧЕНЫ ПАПКИ: {', '.join(include_dirs)}\n")
        if exclude_dirs:
            f.write(f"ИСКЛЮЧЕНЫ ПАПКИ: {', '.join(exclude_dirs)}\n")
        if exclude_files:
            f.write(f"ИСКЛЮЧЕНЫ ФАЙЛЫ: {', '.join(exclude_files)}\n")
        if strip_docstrings_and_comments:
            f.write("РЕЖИМ: УДАЛЕНЫ ДОКСТРОКИ И КОММЕНТАРИИ ИЗ PYTHON-ФАЙЛОВ\n")
        f.write("=" * 60 + "\n\n")

        # Собираем структуру и файлы для листинга
        files_to_list = []

        # Сначала записываем структуру
        for file_path in root_path.rglob('*'):
            if any(exclude in str(file_path) for exclude in exclude_dirs):
                continue

            # Игнорируем сам выходной файл
            if file_path.name == output_file:
                continue

            # Фильтрация по включаемым папкам
            if include_dirs:
                # Проверяем, находится ли файл в одной из включаемых папок
                is_included = False
                for include_dir in include_dirs:
                    include_path = root_path / include_dir
                    try:
                        if include_path in file_path.parents or file_path == include_path:
                            is_included = True
                            break
                    except ValueError:
                        # Может возникнуть если пути на разных дисках
                        continue

                # Также включаем корневые файлы
                if file_path.parent == root_path:
                    is_included = True

                if not is_included:
                    continue

            # Проверка исключения конкретных файлов
            if exclude_files:
                should_exclude = False
                relative_path = file_path.relative_to(root_path)

                for exclude_pattern in exclude_files:
                    # Если исключаемый путь - это абсолютный путь или начинается с /
                    if '/' in exclude_pattern or '\\' in exclude_pattern:
                        # Проверяем совпадение с путем относительно корня
                        if str(relative_path) == exclude_pattern or str(relative_path).startswith(
                                exclude_pattern.rstrip('*')):
                            should_exclude = True
                            break
                    # Иначе проверяем только имя файла
                    else:
                        if file_path.name == exclude_pattern:
                            should_exclude = True
                            break
                        # Проверка на шаблон с *
                        elif '*' in exclude_pattern:
                            import fnmatch
                            if fnmatch.fnmatch(file_path.name, exclude_pattern):
                                should_exclude = True
                                break

                if should_exclude:
                    continue

            relative_path = file_path.relative_to(root_path)

            if file_path.is_file():
                # Включаем файлы с поддерживаемыми расширениями И важные файлы без расширений
                if (file_path.suffix in supported_suffixes or
                        file_path.name in important_files_without_extension or
                        file_path.name.startswith(tuple(important_files_without_extension))):
                    # Записываем файл в структуру
                    indent = "  " * (len(relative_path.parts) - 1)
                    icon = "🐍" if file_path.suffix == '.py' else "📝"
                    f.write(f"{indent}{icon} {relative_path}\n")

                    # Добавляем файл в список для последующего листинга содержимого
                    files_to_list.append(file_path)
            else:
                # Записываем директорию
                indent = "  " * (len(relative_path.parts) - 1)
                f.write(f"{indent}📁 {relative_path}/\n")

        if not files_to_list:
            f.write("\n(Нет поддерживаемых файлов для листинга в проекте)\n")

        # Добавляем листинг содержимого файлов
        f.write("\n" + "=" * 60 + "\n")
        f.write("📜 ЛИСТИНГ СОДЕРЖИМОГО ФАЙЛОВ\n")
        f.write("=" * 60 + "\n\n")

        # Выводим содержимое всех собранных файлов
        for file_path in sorted(files_to_list):
            relative_path = file_path.relative_to(root_path)
            f.write(f"\n{'━' * 80}\n")
            f.write(f"📄 {relative_path}\n")
            f.write(f"{'━' * 80}\n")

            try:
                with open(file_path, 'r', encoding='utf-8') as pf:
                    content = pf.read()

                    if content.strip():
                        # Если флаг установлен и это Python-файл, очищаем код
                        if strip_docstrings_and_comments and file_path.suffix == '.py':
                            original_length = len(content)
                            cleaned_content = strip_python_code(content)
                            cleaned_length = len(cleaned_content)

                            # # Добавляем информацию о сжатии
                            # compression_info = ""
                            # if original_length > 0:
                            #     compression_ratio = (1 - cleaned_length / original_length) * 100
                            #     compression_info = f"\n# 🔥 Сжатие: {compression_ratio:.1f}% ({original_length} → {cleaned_length} символов)\n\n"
                            # else:
                            #     compression_info = "\n# 🔥 Файл обработан (удалены докстроки и комментарии)\n\n"
                            #
                            # f.write(compression_info)
                            f.write(cleaned_content + "\n")
                        else:
                            f.write(content + "\n")
                    else:
                        f.write("# (пустой файл)\n")
            except Exception as e:
                f.write(f"# Ошибка чтения файла: {e}\n")

    print(f"✅ Структура проекта сохранена в: {output_file}")
    print(f"📊 Найдено файлов для листинга: {len(files_to_list)}")

    if strip_docstrings_and_comments:
        print("🔥 Режим: удалены докстроки и комментарии из Python-файлов")

    # Информация о примененных фильтрах
    if include_dirs:
        print(f"📁 Включены папки: {', '.join(include_dirs)}")
    if exclude_dirs:
        print(f"🚫 Исключены папки: {', '.join(exclude_dirs)}")
    if exclude_files:
        print(f"🚫 Исключены файлы: {', '.join(exclude_files)}")


if __name__ == "__main__":
    # Примеры использования:

    # 1. Полная версия (все файлы)
    print("Создание полной версии...")
    get_project_structure(".", "project_structure_full.txt")

    # 2. Только определенные папки
    print("\nСоздание версии с фильтром папок...")
    get_project_structure(
        ".",
        "project_structure_filtered.txt",
        include_dirs=['application', 'presentation']  # Укажите нужные папки
    )

    # 3. С исключением конкретных файлов
    print("\nСоздание версии с исключением файлов...")
    get_project_structure(
        ".",
        "project_structure_excluded.txt",
        exclude_dirs=['.git', '__pycache__', '.vscode', '.idea', 'venv', 'env', 'node_modules', '.github', 'grafana',
                      'elk', 'postgres', 'logs', 'prometheus', 'tests', '.pytest_cache'],
        exclude_files=[
            'gemini_client.*',  # Исключить все файлы с расширением .log
            'huggingface_client.*',  # Исключить все файлы с расширением .log
            'ollama_client.*',  # Исключить все файлы с расширением .log
            'openai_client.*',  # Исключить все файлы с расширением .log
            'generate_struct.*',  # Исключить все файлы с расширением .log
            '__init__.*',  # Исключить все файлы с расширением .log
            # 'config.json',  # Исключить конкретный файл в корне
            # '*.log',  # Исключить все файлы с расширением .log
            # 'secret_*',  # Исключить все файлы, начинающиеся с secret_
            # 'application/config.py',  # Исключить конкретный файл с путем
            # 'temp/',  # Исключить все файлы в папке temp
        ]
    )

    # 4. С удалением докстрок и комментариев (только для Python файлов)
    print("\nСоздание версии с удалением докстрок и комментариев...")
    get_project_structure(
        ".",
        "project_structure_compact.txt",
        exclude_dirs=['.git', '__pycache__', '.vscode', '.idea', 'venv', 'env', 'node_modules', '.github', 'grafana',
                      'elk', 'postgres', 'logs', 'prometheus', 'tests', '.pytest_cache'],
        exclude_files=[
            'gemini_client.*',
            'huggingface_client.*',
            'ollama_client.*',
            'openai_client.*',
            'generate_struct.*',
            '__init__.*',
            '*.log',
            '*.pyc',
        ],
        strip_docstrings_and_comments=True  # <-- НОВЫЙ ФЛАГ
    )

    print("\n🎯 Теперь вы можете отправить мне:")
    print("   • project_structure_full.txt - если нужен полный код")
    print("   • project_structure_filtered.txt - отфильтрованная версия")
    print("   • project_structure_excluded.txt - с исключением файлов")
    print("   • project_structure_compact.txt - компактная версия без докстрок и комментариев")
    print("\n💡 Рекомендую начать с компактной версии, чтобы не перегружать меня!")