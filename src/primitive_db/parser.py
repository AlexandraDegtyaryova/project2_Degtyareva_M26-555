"""Разбор небольшого SQL-подобного языка без выполнения пользовательского кода."""

import json

from primitive_db.constants import (
    ASSIGNMENT_GROUP_SIZE,
    ASSIGNMENT_TOKEN_COUNT,
    MIN_INSERT_TOKEN_COUNT,
    MIN_UPDATE_TOKEN_COUNT,
    SINGLE_QUOTE_ESCAPES,
    VALUE_SEPARATOR,
)


def tokenize(text):
    """Сохранить кавычки и не разделять запятые или пробелы внутри строк."""
    tokens = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        start = position
        character = text[position]
        if character in "(),=":
            tokens.append(character)
            position += 1
        elif character in "\"'":
            quote = character
            position += 1
            while position < len(text) and text[position] != quote:
                if text[position] == "\\":
                    position += 1
                position += 1
            if position >= len(text):
                raise ValueError("проверьте кавычки и экранирование в строке")
            position += 1
            tokens.append(text[start:position])
        else:
            while (
                position < len(text)
                and not text[position].isspace()
                and text[position] not in "(),=\"'\\"
            ):
                position += 1
            if position == start:
                raise ValueError("обратная косая черта допустима только внутри строки")
            tokens.append(text[start:position])
    return tokens


def parse_single_quoted_string(token):
    """Разобрать строку в одинарных кавычках и обычные escape-последовательности."""
    body = token[1:-1]
    result = []
    position = 0
    while position < len(body):
        character = body[position]
        if character == "\\":
            position += 1
            if position >= len(body) or body[position] not in SINGLE_QUOTE_ESCAPES:
                raise ValueError("неподдерживаемое экранирование в строке")
            character = SINGLE_QUOTE_ESCAPES[body[position]]
        result.append(character)
        position += 1
    return "".join(result)


def parse_value(token):
    """Значения: строки в кавычках, целые числа, true и false."""
    if token.startswith('"'):
        try:
            return json.loads(token)
        except json.JSONDecodeError as error:
            raise ValueError("некорректная строка в двойных кавычках") from error
    if token.startswith("'"):
        return parse_single_quoted_string(token)
    if token.lower() in {"true", "false"}:
        return token.lower() == "true"
    digits = token[1:] if token[:1] in {"+", "-"} else token
    if digits and digits.isascii() and digits.isdecimal():
        return int(token)
    raise ValueError(f"{token}: нужны int, bool или строка в кавычках")


def parse_assignments(tokens, multiple=False):
    """Разобрать одно условие или несколько присваиваний через запятую."""
    if not tokens or len(tokens) % ASSIGNMENT_GROUP_SIZE != ASSIGNMENT_TOKEN_COUNT:
        raise ValueError("ожидается столбец = значение")
    if not multiple and len(tokens) != ASSIGNMENT_TOKEN_COUNT:
        raise ValueError("where поддерживает одно условие столбец = значение")
    result = {}
    for index in range(0, len(tokens), ASSIGNMENT_GROUP_SIZE):
        column, equals, value = tokens[index : index + ASSIGNMENT_TOKEN_COUNT]
        if not column.isidentifier() or equals != "=":
            raise ValueError("ожидается столбец = значение")
        if index and tokens[index - 1] != VALUE_SEPARATOR:
            raise ValueError("присваивания set разделяются запятыми")
        if column in result:
            raise ValueError(f"столбец {column} указан повторно")
        result[column] = parse_value(value)
    return result


def parse_where_clause(text):
    """Преобразовать текст условия равенства в словарь."""
    return parse_assignments(tokenize(text))


def parse_set_clause(text):
    """Преобразовать текст присваиваний set в словарь."""
    return parse_assignments(tokenize(text), multiple=True)


def parse_values(text):
    """Прочитать типизированные значения в круглых скобках."""
    tokens = tokenize(text)
    if len(tokens) < 2 or tokens[0] != "(" or tokens[-1] != ")":
        raise ValueError("values должны быть заключены в круглые скобки")
    tokens = tokens[1:-1]
    if not tokens:
        return []
    if len(tokens) % 2 == 0 or any(t != "," for t in tokens[1::2]):
        raise ValueError("значения должны быть разделены запятыми")
    return [parse_value(token) for token in tokens[::2]]


def parse_data_command(text):
    """Проверить грамматику команды и вернуть имя таблицы и её аргументы."""
    tokens = tokenize(text)
    command = tokens[0].lower()
    if command == "info":
        if len(tokens) != 2:
            raise ValueError("ожидается info <имя_таблицы>")
        return {"command": command, "table_name": tokens[1]}

    if command == "insert":
        if (
            len(tokens) < MIN_INSERT_TOKEN_COUNT
            or tokens[1].lower() != "into"
            or tokens[3].lower() != "values"
        ):
            raise ValueError("ожидается insert into <таблица> values (...)")
        return {
            "command": command,
            "table_name": tokens[2],
            "values": parse_values(" ".join(tokens[4:])),
        }

    if command in {"select", "delete"}:
        if len(tokens) < 3 or tokens[1].lower() != "from":
            raise ValueError(f"ожидается {command} from <таблица>")
        condition = None
        if len(tokens) > 3:
            if tokens[3].lower() != "where":
                raise ValueError("после имени таблицы ожидается where")
            condition = parse_assignments(tokens[4:])
        if command == "delete" and condition is None:
            raise ValueError("для delete обязательно условие where")
        return {"command": command, "table_name": tokens[2], "where": condition}

    if command == "update":
        if len(tokens) < MIN_UPDATE_TOKEN_COUNT or tokens[2].lower() != "set":
            raise ValueError("ожидается update <таблица> set ... where ...")
        # Ищем ключевое слово, а не строковое значение "where" в кавычках.
        where_index = next(
            (
                i
                for i in range(3, len(tokens))
                if (i - ASSIGNMENT_TOKEN_COUNT) % ASSIGNMENT_GROUP_SIZE
                == ASSIGNMENT_TOKEN_COUNT
                and tokens[i].lower() == "where"
            ),
            None,
        )
        if where_index is None:
            raise ValueError("для update обязательно условие where")
        return {
            "command": command,
            "table_name": tokens[1],
            "set": parse_assignments(tokens[3:where_index], multiple=True),
            "where": parse_assignments(tokens[where_index + 1 :]),
        }
    raise ValueError(f"неизвестная команда: {command}")
