import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from primitive_db.core import delete, drop_table, insert, select
from primitive_db.decorators import (
    confirm_action,
    create_cacher,
    handle_db_errors,
    log_time,
)


class DecoratorTests(unittest.TestCase):
    def test_errors_are_caught_and_success_value_is_preserved(self):
        cases = [
            (FileNotFoundError(), "Файл данных не найден"),
            (KeyError("users"), "Таблица или столбец"),
            (ValueError("wrong type"), "Ошибка валидации"),
            (PermissionError("read-only"), "Ошибка работы с файлом"),
            (RuntimeError("broken"), "непредвиденная ошибка"),
        ]
        for error, message in cases:

            @handle_db_errors
            def failing():
                raise error

            output = io.StringIO()
            with self.subTest(error=error), contextlib.redirect_stdout(output):
                self.assertIsNone(failing())
            self.assertIn(message, output.getvalue())

        @handle_db_errors
        def add(left, right=0):
            """An example function."""
            return left + right

        self.assertEqual(add(2, right=3), 5)
        self.assertEqual(add.__name__, "add")
        self.assertEqual(add.__doc__, "An example function.")

    def test_confirmation_only_calls_function_after_y(self):
        operation = Mock(return_value={"done": True})
        operation.__name__ = "operation"
        wrapped = confirm_action("тест")(operation)
        for answer in ("n", "", "yes", "да", "anything", "Y", " y "):
            with (
                self.subTest(answer=answer),
                patch("builtins.input", return_value=answer) as read,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertIsNone(wrapped(1, flag=True))
                read.assert_called_once_with(
                    'Вы уверены, что хотите выполнить "тест"? [y/n]: '
                )
        operation.assert_not_called()
        with patch("builtins.input", return_value="y"):
            self.assertEqual(wrapped(1, flag=True), {"done": True})
        operation.assert_called_once_with(1, flag=True)

    def test_timing_uses_monotonic_and_preserves_result(self):
        @log_time
        def calculation():
            return 42

        output = io.StringIO()
        with (
            patch("primitive_db.decorators.time.monotonic", side_effect=[1.0, 1.125]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(calculation(), 42)
        self.assertEqual(
            output.getvalue().strip(),
            "Функция calculation выполнилась за 0.125 секунд",
        )
        self.assertEqual(calculation.__name__, "calculation")

    def test_cacher_is_a_closure_with_independent_instances(self):
        cache = create_cacher()
        other_cache = create_cacher()
        compute = Mock(return_value=[])
        self.assertEqual(cache("query", compute), [])
        self.assertEqual(cache("query", compute), [])
        compute.assert_called_once_with()
        self.assertEqual(other_cache("query", compute), [])
        self.assertEqual(compute.call_count, 2)
        self.assertIsNotNone(cache.__closure__)

    def test_failed_computation_is_not_cached(self):
        cache = create_cacher()
        compute = Mock(side_effect=[ValueError("failed"), 42])
        with self.assertRaises(ValueError):
            cache("query", compute)
        self.assertEqual(cache("query", compute), 42)
        self.assertEqual(compute.call_count, 2)

    def test_actual_core_wrappers_preserve_function_names(self):
        for function in (insert, select, delete, drop_table):
            self.assertTrue(hasattr(function, "__wrapped__"))
        self.assertEqual(select.__name__, "select")


class SelectCacheTests(unittest.TestCase):
    def test_repeated_query_is_cached_and_changes_refresh_result(self):
        data = [{"ID": 873512, "age": 28, "tag": "cache-test"}]
        original_matches = __import__("primitive_db.core", fromlist=["matches"]).matches
        with (
            patch("primitive_db.core.matches", wraps=original_matches) as matches,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            first = select(data, {"age": 28})
            first[0]["age"] = 100
            self.assertEqual(select(data, {"age": 28})[0]["age"], 28)
            self.assertEqual(matches.call_count, 1)
            data[0]["age"] = 29
            self.assertEqual(select(data, {"age": 28}), [])
            self.assertEqual(matches.call_count, 2)
            data.append({"ID": 873513, "age": 28, "tag": "cache-test"})
            self.assertEqual(len(select(data, {"age": 28})), 1)
            data.pop()
            self.assertEqual(select(data, {"age": 28}), [])

    def test_equal_python_values_of_different_types_have_different_keys(self):
        data = [{"ID": 765412, "flag": True}]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(select(data, {"flag": 1}), [])
            self.assertEqual(len(select(data, {"flag": True})), 1)


class ConfirmedSessionTests(unittest.TestCase):
    def session(self, folder, commands):
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, "-m", "primitive_db.main"],
            input="\n".join(commands) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=folder,
            env=environment,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_cancelled_deletions_leave_files_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            self.session(
                folder,
                ["create_table users age:int", "insert into users values (28)", "exit"],
            )
            meta = Path(folder) / "db_meta.json"
            data = Path(folder) / "data" / "users.json"
            before = (meta.read_bytes(), data.read_bytes())
            output = self.session(
                folder,
                [
                    "delete from users where ID=1",
                    "n",
                    "drop_table users",
                    "n",
                    "info users",
                    "exit",
                ],
            )
            self.assertEqual(before, (meta.read_bytes(), data.read_bytes()))
            self.assertEqual(output.count("отменена."), 2)
            self.assertNotIn("успешно удалена", output)
            self.assertIn("Количество записей: 1", output)

    def test_confirmed_deletions_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            output = self.session(
                folder,
                [
                    "create_table users age:int",
                    "insert into users values (28)",
                    "delete from users where ID=1",
                    "y",
                    "info users",
                    "drop_table users",
                    "y",
                    "exit",
                ],
            )
            self.assertIn("ID=1 успешно удалена", output)
            self.assertIn("Количество записей: 0", output)
            metadata = json.loads((Path(folder) / "db_meta.json").read_text("utf-8"))
            self.assertEqual(metadata, {})
            self.assertFalse((Path(folder) / "data" / "users.json").exists())

    def test_same_query_changes_after_insert_update_delete_and_recreate(self):
        with tempfile.TemporaryDirectory() as folder:
            output = self.session(
                folder,
                [
                    "create_table users age:int",
                    "insert into users values (28)",
                    "select from users where age=28",
                    "select from users where age=28",
                    "update users set age=29 where ID=1",
                    "select from users where age=28",
                    "insert into users values (28)",
                    "select from users where age=28",
                    "delete from users where age=28",
                    "y",
                    "select from users where age=28",
                    "drop_table users",
                    "y",
                    "create_table users age:int",
                    "select from users where age=28",
                    "info users",
                    "exit",
                ],
            )
            # Пустой результат тоже таблица, но строка с 28 не должна воскресать.
            self.assertEqual(output.count("| 1  |  28 |"), 2)
            self.assertEqual(output.count("| 2  |  28 |"), 1)
            self.assertIn("Количество записей: 0", output)

    def test_validation_error_does_not_save_none_or_stop_loop(self):
        with tempfile.TemporaryDirectory() as folder:
            output = self.session(
                folder,
                [
                    "create_table users age:int",
                    "insert into users values (true)",
                    "insert into users values (28)",
                    "update users set ID=5 where ID=1",
                    "info users",
                    "exit",
                ],
            )
            self.assertEqual(output.count("Ошибка валидации:"), 2)
            data = json.loads((Path(folder) / "data" / "users.json").read_text("utf-8"))
            self.assertEqual(data, [{"ID": 1, "age": 28}])
            self.assertIn("Количество записей: 1", output)


if __name__ == "__main__":
    unittest.main()
