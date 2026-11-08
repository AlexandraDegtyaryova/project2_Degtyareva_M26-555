import json
import shlex

import prompt
from prettytable import PrettyTable

from primitive_db.core import (
    create_table,
    delete,
    drop_table,
    get_schema,
    insert,
    select,
    update,
    validate_fields,
    validate_table_data,
)
from primitive_db.decorators import handle_db_errors
from primitive_db.parser import parse_data_command
from primitive_db.utils import (
    load_metadata,
    load_table_data,
    remove_table_data,
    save_metadata,
    save_table_data,
)

METADATA_FILE = "db_meta.json"
DATA_COMMANDS = {"insert", "select", "update", "delete", "info"}
TABLE_COMMANDS = {"create_table", "drop_table", "list_tables", "help", "exit"}


def print_help():
    """Показать команды управления таблицами и записями."""
    print("\n***Процесс работы с таблицей***")
    print("<command> create_table <имя> <столбец:тип> .. - создать таблицу")
    print("<command> list_tables - показать список всех таблиц")
    print("<command> drop_table <имя> - удалить таблицу")
    print("\n***Операции с данными***")
    print("<command> insert into <имя> values (<значение1>, ...) - создать запись")
    print("<command> select from <имя> [where <столбец> = <значение>] - прочитать")
    print("<command> update <имя> set <столбец> = <значение> where ... - обновить")
    print("<command> delete from <имя> where <столбец> = <значение> - удалить")
    print("<command> info <имя> - информация о таблице")
    print("\nОбщие команды:")
    print("<command> exit - выход из программы")
    print("<command> help - справочная информация\n")


def handle_table_command(metadata, args):
    """Сохранить прежнее управление схемой и связать его с файлами данных."""
    command, *arguments = args
    if (
        (command in {"help", "list_tables"} and arguments)
        or (command == "drop_table" and len(arguments) != 1)
        or (command == "create_table" and len(arguments) < 2)
    ):
        raise ValueError("неверное количество аргументов команды")

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
        table_name = arguments[0]
        if command == "create_table":
            result = create_table(metadata, table_name, arguments[1:])
        else:
            result = drop_table(metadata, table_name)
        if result is None:
            return
        metadata = result
        if metadata != previous_metadata:
            if command == "create_table":
                save_table_data(table_name, [])
            save_metadata(METADATA_FILE, metadata)
            if command == "drop_table":
                remove_table_data(table_name)


def print_records(schema, records):
    table = PrettyTable()
    table.field_names = list(schema)
    for row in records:
        table.add_row([row[column] for column in schema])
    print(table)


def handle_data_command(metadata, parsed):
    command = parsed["command"]
    table_name = parsed["table_name"]
    if table_name not in metadata:
        raise KeyError(table_name)
    schema = get_schema(metadata, table_name)

    if command == "insert":
        # Сигнатура insert из ТЗ не принимает данные: она загружает их сама.
        table_data = insert(metadata, table_name, parsed["values"])
        if table_data is None:
            return
        save_table_data(table_name, table_data)
        new_id = table_data[-1]["ID"]
        print(f'Запись с ID={new_id} успешно добавлена в таблицу "{table_name}".')
        return

    table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)
    if command == "info":
        print(f"Таблица: {table_name}")
        print(f"Столбцы: {', '.join(metadata[table_name])}")
        print(f"Количество записей: {len(table_data)}")
        return

    where_clause = parsed["where"]
    if where_clause is not None:
        validate_fields(schema, where_clause)
    if command == "select":
        records = select(table_data, where_clause)
        if records is not None:
            print_records(schema, records)
        return

    if command == "update":
        validate_fields(schema, parsed["set"])
    matching_rows = select(table_data, where_clause)
    if not matching_rows:
        print("Подходящих записей не найдено.")
        return

    if command == "update":
        new_data = update(table_data, parsed["set"], where_clause)
    else:
        new_data = delete(table_data, where_clause)
    if new_data is None:
        return
    save_table_data(table_name, new_data)
    for row in matching_rows:
        if command == "update":
            print(
                f'Запись с ID={row["ID"]} в таблице "{table_name}" успешно обновлена.'
            )
        else:
            print(f'Запись с ID={row["ID"]} успешно удалена из таблицы "{table_name}".')


@handle_db_errors
def execute_command(metadata, user_input):
    """Обрабатывать ошибки разбора, валидации и файлов на одной границе."""
    command = user_input.split(maxsplit=1)[0].lower()
    if command not in DATA_COMMANDS | TABLE_COMMANDS:
        print(f"Функции {command} нет. Попробуйте снова.")
        return False
    if command in DATA_COMMANDS:
        handle_data_command(metadata, parse_data_command(user_input))
    else:
        args = shlex.split(user_input)
        args[0] = command
        if command == "exit":
            if len(args) != 1:
                raise ValueError("exit не принимает аргументы")
            return True
        handle_table_command(metadata, args)
    return False


def run():
    """Основной цикл: чтение -> разбор -> проверка -> операция -> сохранение."""
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
        if not user_input.strip():
            continue
        if execute_command(metadata, user_input) is True:
            return
