"""Функциональные проверки без классов и стороннего тестового фреймворка."""

import json
import os

from primitive_db import constants, core, decorators, engine, parser, utils

MESSAGES = []
ANSWERS = []
SCHEMA = {"users": ["ID:int", "name:str", "age:int", "active:bool"]}


def record_message(*values, **options):
    """Собрать вывод приложения для проверки сообщений и таблиц."""
    MESSAGES.append(options.get("sep", " ").join(str(value) for value in values))


def read_answer(message):
    """Запомнить запрос подтверждения и вернуть подготовленный ответ."""
    MESSAGES.append(message)
    if not ANSWERS:
        raise EOFError
    return ANSWERS.pop(0)


def execute(command, answer="y"):
    """Выполнить команду с актуальными файлами и заданным подтверждением."""
    ANSWERS[:] = [answer]
    return engine.execute_command(utils.load_metadata(constants.META_FILE), command)


def seed():
    """Создать таблицу с двумя записями для сценариев CRUD."""
    execute("create_table users name:str age:int active:bool")
    execute('insert into users values ("Sergei", 28, true)')
    execute('insert into users values ("Ира, where", 31, false)')


def rows():
    """Прочитать записи основной тестовой таблицы."""
    return utils.load_table_data("users")


def read_bytes(path):
    """Получить точное содержимое файла, включая форматирование."""
    with open(path, "rb") as file:
        return file.read()


def expect_error(exception_type, function, *args):
    """Проверить исключение вспомогательной недекорированной функции."""
    try:
        function(*args)
    except exception_type:
        return
    raise AssertionError(f"Ожидалось исключение {exception_type.__name__}")


def test_missing_metadata():
    """Первый запуск не требует заранее созданного файла."""
    assert utils.load_metadata(constants.META_FILE) == {}


def test_create_schema():
    """Автоматический ID идёт первым, а файл записей начинается с []."""
    execute("create_table users name:str age:int active:bool")
    assert utils.load_metadata(constants.META_FILE) == SCHEMA
    assert rows() == []


def test_explicit_id():
    """Явный ID не дублируется и переносится в начало схемы."""
    execute("create_table users name:str ID:int age:int")
    assert utils.load_metadata(constants.META_FILE)["users"] == [
        "ID:int",
        "name:str",
        "age:int",
    ]


def test_duplicate_table():
    """Повторное создание не заменяет структуру и данные."""
    seed()
    before = read_bytes(constants.META_FILE), read_bytes(utils.table_filepath("users"))
    execute("create_table users title:str")
    assert before == (
        read_bytes(constants.META_FILE),
        read_bytes(utils.table_filepath("users")),
    )
    assert any("уже существует" in message for message in MESSAGES)


def test_bad_columns():
    """Неверные типы, имена и повторы не создают частичную таблицу."""
    for description in (
        "age:float",
        "name:str name:int",
        "ID:str",
        "ID:int ID:int",
        "broken",
        "age:int:bool",
        ":str",
        "1age:int",
    ):
        execute(f"create_table users {description}")
        assert utils.load_metadata(constants.META_FILE) == {}


def test_bad_table_name():
    """Недопустимое имя не превращается в путь к файлу."""
    execute("create_table ../users name:str")
    assert not os.path.exists(constants.META_FILE)
    expect_error(ValueError, utils.table_filepath, "../users")


def test_insert_all_types():
    """Все значения сохраняются с точными типами и автоматическими ID."""
    seed()
    assert rows() == [
        {"ID": 1, "name": "Sergei", "age": 28, "active": True},
        {"ID": 2, "name": "Ира, where", "age": 31, "active": False},
    ]


def test_required_values():
    """Пропущенные и лишние значения, включая явный ID, отклоняются."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    for values in ('("A", 28)', '(9, "A", 28, true)', "()"):
        execute(f"insert into users values {values}")
        assert read_bytes(utils.table_filepath("users")) == before


def test_strict_types():
    """bool не подменяет int, а строки и числа не преобразуются неявно."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    for values in ('("A", true, false)', "(28, 28, true)", '("A", 28, 1)'):
        execute(f"insert into users values {values}")
        assert read_bytes(utils.table_filepath("users")) == before


def test_empty_string_and_zero():
    """Явно переданные пустая строка, ноль и false являются значениями."""
    execute("create_table users name:str age:int active:bool")
    execute('insert into users values ("", 0, false)')
    assert rows() == [{"ID": 1, "name": "", "age": 0, "active": False}]


def test_select_all_and_where():
    """Выборка возвращает все или только подходящие записи."""
    seed()
    assert len(core.select(rows())) == 2
    assert core.select(rows(), {"age": 28})[0]["name"] == "Sergei"
    assert core.select(rows(), {"ID": True}) == []


def test_prettytable():
    """Консольная выборка имеет заголовки, границы и значения."""
    seed()
    execute("select from users where age=28")
    rendered = MESSAGES[-1]
    assert "+----+" in rendered and "| ID |" in rendered and "Sergei" in rendered


def test_update_multiple_fields():
    """Обновляются все присваивания и только подходящие записи."""
    seed()
    execute('update users set age=29, active=false where name="Sergei"')
    assert rows()[0] == {"ID": 1, "name": "Sergei", "age": 29, "active": False}
    assert rows()[1]["age"] == 31


def test_bad_updates():
    """ID, неизвестный столбец и неверный тип не изменяют файл."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    for assignment in ('age="29"', "ID=9", "unknown=1"):
        execute(f"update users set {assignment} where ID=1")
        assert read_bytes(utils.table_filepath("users")) == before


def test_delete_cancel():
    """Отказ от удаления оставляет байты файла без изменений."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    execute("delete from users where ID=1", "n")
    assert read_bytes(utils.table_filepath("users")) == before
    assert "отменена" in MESSAGES[-1]


def test_delete_confirm():
    """Подтверждённое удаление сохраняет оставшиеся записи."""
    seed()
    execute("delete from users where ID=1", "y")
    assert [row["ID"] for row in rows()] == [2]


def test_id_gaps():
    """Удаление промежуточной записи не создаёт одинаковых ID."""
    seed()
    execute("delete from users where ID=1")
    execute('insert into users values ("New", 20, true)')
    assert [row["ID"] for row in rows()] == [2, 3]


def test_drop_cancel():
    """Отказ от удаления таблицы сохраняет метаданные и записи."""
    seed()
    before = read_bytes(constants.META_FILE), read_bytes(utils.table_filepath("users"))
    execute("drop_table users", "n")
    assert before == (
        read_bytes(constants.META_FILE),
        read_bytes(utils.table_filepath("users")),
    )


def test_drop_confirm_and_recreate():
    """Пересоздание удалённой таблицы не возвращает старые строки."""
    seed()
    execute("drop_table users")
    assert utils.load_metadata(constants.META_FILE) == {}
    assert not os.path.exists(utils.table_filepath("users"))
    execute("create_table users title:str")
    assert rows() == []


def test_info():
    """Информация включает имя, структуру и число записей."""
    seed()
    execute("info users")
    assert MESSAGES[-3:] == [
        "Таблица: users",
        "Столбцы: ID:int, name:str, age:int, active:bool",
        "Количество записей: 2",
    ]


def test_persistence():
    """Повторное чтение файлов восстанавливает структуру и записи."""
    seed()
    with open(constants.META_FILE, encoding="utf-8") as file:
        assert json.load(file) == SCHEMA
    with open(utils.table_filepath("users"), encoding="utf-8") as file:
        assert json.load(file) == rows()


def test_corrupted_data():
    """Повреждённый файл не перезаписывается после ошибки операции."""
    seed()
    path = utils.table_filepath("users")
    for content in ("{broken", "{}", '[{"ID": 1}]'):
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
        before = read_bytes(path)
        execute('insert into users values ("A", 20, true)')
        assert read_bytes(path) == before


def test_parser_strings():
    """Запятые, пробелы и служебные слова внутри кавычек сохраняются."""
    assert parser.parse_values('("Doe, Jane = where", -28, false)') == [
        "Doe, Jane = where",
        -28,
        False,
    ]
    assert parser.parse_values("('Ира', +28, true)") == ["Ира", 28, True]
    assert parser.parse_values(r"""('O\'Brien', 28, true)""")[0] == "O'Brien"
    assert parser.parse_values(r'("A\"B", 28, true)')[0] == 'A"B'


def test_parser_conditions():
    """where и set преобразуются в словари с типизированными значениями."""
    assert parser.parse_where_clause("age=28") == {"age": 28}
    assert parser.parse_set_clause('name="where, set", age=29') == {
        "name": "where, set",
        "age": 29,
    }
    command = parser.parse_data_command(
        'update users set where="where", age=29 where name="Ира"'
    )
    assert command["set"] == {"where": "where", "age": 29}


def test_parser_rejects_invalid_input():
    """Незакрытые строки, пропущенные запятые и неподдерживаемые типы ошибочны."""
    for text in (
        "(Sergei, 28, true)",
        '("A", 28, true,)',
        '("A" 28, true)',
        '("A", 2.8, true)',
        '("A", null, true)',
        '("unclosed, 28, true)',
    ):
        expect_error(ValueError, parser.parse_values, text)


def test_where_required_for_changes():
    """Команды update и delete без where не затрагивают все строки."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    execute("delete from users")
    execute("update users set age=29")
    assert read_bytes(utils.table_filepath("users")) == before


def test_confirmation_factory():
    """Опасная функция вызывается только после точного ответа y."""
    calls = []

    @decorators.confirm_action("тест")
    def operation():
        """Запомнить фактическое выполнение тестового действия."""
        calls.append(True)
        return 42

    for answer in ("n", "", "yes", "Y", " y "):
        ANSWERS[:] = [answer]
        assert operation() is None
    assert not calls
    ANSWERS[:] = ["y"]
    assert operation() == 42 and calls == [True]


def test_error_decorator():
    """Декоратор перехватывает все обязательные виды исключений."""
    for error in (FileNotFoundError(), KeyError("users"), ValueError("type")):

        @decorators.handle_db_errors
        def operation():
            """Сгенерировать ошибку для проверки общей обработки."""
            raise error

        assert operation() is None
    assert any("Файл данных не найден" in message for message in MESSAGES)
    assert any("Таблица или столбец" in message for message in MESSAGES)
    assert any("Ошибка валидации" in message for message in MESSAGES)


def test_timing():
    """Время берётся из monotonic и выводится с тремя знаками."""
    original = decorators.time.monotonic
    moments = iter([1.0, 1.125])

    @decorators.log_time
    def operation():
        """Вернуть проверяемый результат функции."""
        return 42

    try:
        decorators.time.monotonic = lambda: next(moments)
        assert operation() == 42
    finally:
        decorators.time.monotonic = original
    assert MESSAGES[-1] == "Функция operation выполнилась за 0.125 секунд"


def test_function_metadata():
    """Обёртки сохраняют имя, документацию и ссылку на исходную функцию."""
    for function in (core.insert, core.select, core.delete, core.drop_table):
        assert function.__name__ == function.__wrapped__.__name__
        assert function.__doc__


def test_cacher_hits_and_empty_result():
    """Даже пустой результат вычисляется только один раз для ключа."""
    cache = decorators.create_cacher()
    calls = []

    def compute():
        """Посчитать вызовы источника данных."""
        calls.append(True)
        return []

    assert cache("key", compute) == []
    assert cache("key", compute) == []
    assert len(calls) == 1 and cache.__closure__


def test_independent_caches():
    """Каждое замыкание хранит собственный словарь."""
    first, second = decorators.create_cacher(), decorators.create_cacher()
    assert first("key", lambda: 1) == 1
    assert second("key", lambda: 2) == 2


def test_failed_computation_not_cached():
    """Ошибка источника не становится сохранённым значением кэша."""
    cache = decorators.create_cacher()

    def broken():
        """Отклонить первое вычисление."""
        raise ValueError("broken")

    expect_error(ValueError, cache, "key", broken)
    assert cache("key", lambda: 42) == 42


def test_select_uses_cache():
    """Повторная выборка не запускает фильтр заново."""
    original = core.matches
    calls = []

    def count_matches(row, condition):
        """Посчитать реальные вызовы фильтра строк."""
        calls.append(True)
        return original(row, condition)

    try:
        core.matches = count_matches
        data = [{"ID": 991827, "age": 76}]
        assert len(core.select(data, {"age": 76})) == 1
        assert len(core.select(data, {"age": 76})) == 1
        assert len(calls) == 1
    finally:
        core.matches = original


def test_select_cache_refresh_and_copies():
    """Изменение исходных данных и результата не портит кэш."""
    data = [{"ID": 79123, "age": 28}]
    first = core.select(data, {"age": 28})
    first[0]["age"] = 100
    assert core.select(data, {"age": 28})[0]["age"] == 28
    data[0]["age"] = 29
    assert core.select(data, {"age": 28}) == []
    data.append({"ID": 79124, "age": 28})
    assert len(core.select(data, {"age": 28})) == 1


def test_cached_query_after_crud():
    """Один запрос получает актуальный результат после каждой CRUD-операции."""
    seed()
    assert len(core.select(rows(), {"age": 28})) == 1
    execute("update users set age=29 where ID=1")
    assert core.select(rows(), {"age": 28}) == []
    execute('insert into users values ("New", 28, true)')
    assert len(core.select(rows(), {"age": 28})) == 1
    execute("delete from users where age=28")
    assert core.select(rows(), {"age": 28}) == []


def test_no_none_is_saved():
    """Ошибка декорированной функции не заменяет JSON значением null."""
    seed()
    before = read_bytes(utils.table_filepath("users"))
    execute('insert into users values ("A", true, false)')
    execute("update users set ID=9 where ID=1")
    assert read_bytes(utils.table_filepath("users")) == before


def test_unknown_command_and_exit():
    """Неизвестная команда оставляет цикл рабочим, exit завершает сеанс."""
    assert execute("unknown") is False
    assert any("Функции unknown нет" in message for message in MESSAGES)
    assert execute("exit") is True


def test_run_loop():
    """Полный цикл умеет продолжаться после ошибки и выйти по exit."""
    original = engine.prompt.string
    commands = iter(["unknown", "create_table users age:int", "info users", "exit"])
    try:
        engine.prompt.string = lambda _: next(commands)
        engine.run()
    finally:
        engine.prompt.string = original
    assert any("Количество записей: 0" in message for message in MESSAGES)


def test_source_constraints():
    """В приложении нет классов и импортов вне разрешённого списка."""
    allowed = {"json", "shlex", "time", "os", "prettytable", "prompt", "primitive_db"}
    package = os.path.dirname(core.__file__)
    for filename in os.listdir(package):
        if not filename.endswith(".py"):
            continue
        with open(os.path.join(package, filename), encoding="utf-8") as file:
            for line in file:
                assert not line.lstrip().startswith("class "), filename
                if line.startswith(("import ", "from ")):
                    assert line.split()[1].split(".")[0] in allowed, line


def test_docstrings():
    """Публичные функции приложения имеют описания."""
    for module in (core, decorators, engine, parser, utils):
        for name, value in vars(module).items():
            if (
                callable(value)
                and getattr(value, "__module__", None) == module.__name__
            ):
                assert value.__doc__, f"{module.__name__}.{name}"


def remove_test_directory(path, test_root):
    """Удалить только созданную тестом папку после проверки её границ."""
    path, test_root = os.path.realpath(path), os.path.realpath(test_root)
    if os.path.commonpath([path, test_root]) != test_root or path == test_root:
        raise ValueError("отказ от удаления за пределами тестовой папки")
    for folder, directories, files in os.walk(path, topdown=False):
        for filename in files:
            os.remove(os.path.join(folder, filename))
        for directory in directories:
            os.rmdir(os.path.join(folder, directory))
    os.rmdir(path)


def run_tests():
    """Запустить независимые функциональные проверки с временными файлами."""
    origin = os.getcwd()
    test_root = os.path.join(origin, ".test-data")
    os.makedirs(test_root, exist_ok=True)
    functions = sorted(
        (name, value)
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    failures = []
    for name, function in functions:
        path = os.path.join(test_root, name + "-" + os.urandom(6).hex())
        os.mkdir(path)
        MESSAGES.clear()
        for module in (core, decorators, engine):
            module.print = record_message
        decorators.input = read_answer
        try:
            os.chdir(path)
            function()
        except Exception as error:
            failures.append(name)
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            print(f"PASS {name}")
        finally:
            os.chdir(origin)
            for module in (core, decorators, engine):
                del module.print
            del decorators.input
            remove_test_directory(path, test_root)
    if not os.listdir(test_root):
        os.rmdir(test_root)
    print(f"Checks: {len(functions)}; failures: {len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
