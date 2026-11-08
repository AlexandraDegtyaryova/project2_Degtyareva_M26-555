SUPPORTED_TYPES = {"int", "str", "bool"}


def create_table(metadata, table_name, columns):
    """Проверить описание столбцов и добавить новую таблицу в metadata."""
    if table_name in metadata:
        print(f'Ошибка: Таблица "{table_name}" уже существует.')
        return metadata

    if not table_name.isidentifier():
        print(f"Некорректное значение: {table_name}. Попробуйте снова.")
        return metadata

    if not columns:
        print("Некорректное значение: не указаны столбцы. Попробуйте снова.")
        return metadata

    # Сначала проверяем ВСЕ столбцы, затем меняем metadata.
    validated_columns = ["ID:int"]
    column_names = set()
    for column in columns:
        parts = column.split(":")
        if len(parts) != 2:
            print(f"Некорректное значение: {column}. Попробуйте снова.")
            return metadata

        name, data_type = parts
        if (
            not name.isidentifier()
            or data_type not in SUPPORTED_TYPES
            or name in column_names
            or (name == "ID" and data_type != "int")
        ):
            print(f"Некорректное значение: {column}. Попробуйте снова.")
            return metadata

        column_names.add(name)
        if name != "ID":
            validated_columns.append(column)

    metadata[table_name] = validated_columns
    print(
        f'Таблица "{table_name}" успешно создана со столбцами: '
        f"{', '.join(validated_columns)}"
    )
    return metadata


def drop_table(metadata, table_name):
    """Удалить описание существующей таблицы."""
    if table_name not in metadata:
        print(f'Ошибка: Таблица "{table_name}" не существует.')
        return metadata

    del metadata[table_name]
    print(f'Таблица "{table_name}" успешно удалена.')
    return metadata
