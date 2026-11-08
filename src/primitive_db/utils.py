import json
from pathlib import Path


def load_metadata(filepath):
    """Загрузить структуру таблиц; при первом запуске вернуть пустой словарь."""
    try:
        with open(filepath, encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_metadata(filepath, data):
    """Сохранить структуру таблиц в JSON."""
    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")


def table_filepath(table_name):
    """Имена таблиц не должны превращаться в пути к посторонним файлам."""
    if not table_name.isidentifier():
        raise ValueError(f"неверное имя таблицы: {table_name}")
    return Path("data") / f"{table_name}.json"


def load_table_data(table_name):
    """Прочитать список записей таблицы; отсутствующий файл означает []."""
    try:
        with table_filepath(table_name).open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError(f"данные таблицы {table_name} должны быть списком записей")
    return data


def save_table_data(table_name, data):
    """Создать data/ при необходимости и сохранить записи таблицы."""
    filepath = table_filepath(table_name)
    filepath.parent.mkdir(exist_ok=True)
    save_metadata(filepath, data)


def remove_table_data(table_name):
    """Удалить файл при удалении таблицы, чтобы старые записи не вернулись."""
    table_filepath(table_name).unlink(missing_ok=True)
