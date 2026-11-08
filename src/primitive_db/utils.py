import json


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
