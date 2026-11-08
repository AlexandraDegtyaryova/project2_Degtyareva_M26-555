from primitive_db.utils import load_table_data

SUPPORTED_TYPES = {"int", "str", "bool"}
PYTHON_TYPES = {"int": int, "str": str, "bool": bool}


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


def get_schema(metadata, table_name):
    """Получить отображение имя столбца -> имя типа."""
    if table_name not in metadata:
        raise ValueError(f'Таблица "{table_name}" не существует')
    return dict(column.split(":") for column in metadata[table_name])


def validate_fields(schema, fields):
    """Проверить имена и точные типы: bool не должен приниматься вместо int."""
    for column, value in fields.items():
        if column not in schema:
            raise ValueError(f"неизвестный столбец: {column}")
        expected_type = PYTHON_TYPES[schema[column]]
        if type(value) is not expected_type:
            raise ValueError(f"{column} ожидает {schema[column]}, получено {value!r}")


def validate_table_data(schema, table_data):
    """Повреждённые записи не должны быть перезаписаны новой операцией."""
    ids = set()
    for row in table_data:
        if set(row) != set(schema):
            raise ValueError("сохранённая запись не соответствует столбцам таблицы")
        validate_fields(schema, row)
        if row["ID"] < 1 or row["ID"] in ids:
            raise ValueError("сохранённые ID должны быть положительными и уникальными")
        ids.add(row["ID"])


def insert(metadata, table_name, values):
    """Проверить значения и вернуть данные с новой записью, не сохраняя их."""
    schema = get_schema(metadata, table_name)
    columns = [name for name in schema if name != "ID"]
    if len(values) != len(columns):
        raise ValueError(
            f"ожидалось значений: {len(columns)} (без ID), получено: {len(values)}"
        )
    fields = dict(zip(columns, values, strict=True))
    validate_fields(schema, fields)
    table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)
    new_id = max((row["ID"] for row in table_data), default=0) + 1
    return [*table_data, {"ID": new_id, **fields}]


def matches(row, where_clause):
    """Условие использует равенство значений одинакового типа."""
    return all(
        column in row and type(row[column]) is type(value) and row[column] == value
        for column, value in where_clause.items()
    )


def select(table_data, where_clause=None):
    """Вернуть все записи или записи, удовлетворяющие условию."""
    if where_clause is None:
        return list(table_data)
    return [row for row in table_data if matches(row, where_clause)]


def update(table_data, set_clause, where_clause):
    """Вернуть записи с обновлёнными полями; ID изменять нельзя."""
    if "ID" in set_clause:
        raise ValueError("ID генерируется автоматически и не изменяется")
    return [
        {**row, **set_clause} if matches(row, where_clause) else dict(row)
        for row in table_data
    ]


def delete(table_data, where_clause):
    """Вернуть записи, которые не удовлетворяют условию удаления."""
    return [row for row in table_data if not matches(row, where_clause)]
