import json
import shlex

import prompt

from primitive_db.core import create_table, drop_table
from primitive_db.utils import load_metadata, save_metadata

METADATA_FILE = "db_meta.json"


def print_help():
    """Показать доступные команды управления таблицами."""
    print("\n***Процесс работы с таблицей***")
    print("Функции:")
    print("<command> create_table <имя_таблицы> <столбец1:тип> .. - создать таблицу")
    print("<command> list_tables - показать список всех таблиц")
    print("<command> drop_table <имя_таблицы> - удалить таблицу")
    print("\nОбщие команды:")
    print("<command> exit - выход из программы")
    print("<command> help - справочная информация\n")


def run():
    """Загружать метаданные, обрабатывать команды и сохранять изменения."""
    print("***База данных***")
    print_help()

    while True:
        try:
            metadata = load_metadata(METADATA_FILE)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Ошибка чтения метаданных: {error}")
            return

        if not isinstance(metadata, dict):
            print("Ошибка: метаданные должны содержать JSON-объект с таблицами.")
            return

        try:
            user_input = prompt.string(">>>Введите команду: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        try:
            args = shlex.split(user_input)
        except ValueError:
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            continue

        if not args:
            continue

        command = args[0]
        arguments = args[1:]
        if command not in {"exit", "help", "list_tables", "create_table", "drop_table"}:
            print(f"Функции {command} нет. Попробуйте снова.")
            continue

        if (
            (command in {"exit", "help", "list_tables"} and arguments)
            or (command == "drop_table" and len(arguments) != 1)
            or (command == "create_table" and len(arguments) < 2)
        ):
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            continue

        if command == "exit":
            return
        if command == "help":
            print_help()
        elif command == "list_tables":
            if metadata:
                for table_name in metadata:
                    print(f"- {table_name}")
            else:
                print("Таблиц пока нет.")
        else:
            previous_metadata = metadata.copy()
            if command == "create_table":
                metadata = create_table(metadata, arguments[0], arguments[1:])
            else:
                metadata = drop_table(metadata, arguments[0])

            # Ошибочная команда не должна перезаписывать файл.
            if metadata != previous_metadata:
                try:
                    save_metadata(METADATA_FILE, metadata)
                except OSError as error:
                    print(f"Ошибка: изменения не сохранены в файл: {error}")
