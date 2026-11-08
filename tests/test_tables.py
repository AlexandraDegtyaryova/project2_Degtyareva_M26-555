import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primitive_db.core import create_table, drop_table
from primitive_db.engine import run
from primitive_db.utils import load_metadata, save_metadata


class TableTests(unittest.TestCase):
    def call(self, function, *args):
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("builtins.input", return_value="y"),
        ):
            result = function(*args)
        return result, output.getvalue()

    def test_create_and_drop(self):
        metadata = {}
        result, message = self.call(
            create_table, metadata, "users", ["name:str", "age:int", "active:bool"]
        )
        self.assertIs(result, metadata)
        self.assertEqual(
            metadata["users"], ["ID:int", "name:str", "age:int", "active:bool"]
        )
        self.assertIn('Таблица "users" успешно создана', message)
        result, message = self.call(drop_table, metadata, "users")
        self.assertEqual(result, {})
        self.assertIn("успешно удалена", message)

    def test_existing_table_not_replaced(self):
        metadata = {"users": ["ID:int", "age:int"]}
        original = copy.deepcopy(metadata)
        _, message = self.call(create_table, metadata, "users", ["name:str"])
        self.assertEqual(metadata, original)
        self.assertIn("уже существует", message)

    def test_invalid_columns_never_partially_create_table(self):
        for columns in (
            ["name:str", "age:float"],
            ["name:str", "name:bool"],
            ["name:str", "broken"],
            ["name:str", "age:int:bool"],
            ["name:str", ":str"],
            ["name:str", "1age:int"],
            ["ID:str"],
            ["ID:int", "ID:int"],
            [],
        ):
            with self.subTest(columns=columns):
                metadata = {"existing": ["ID:int"]}
                original = copy.deepcopy(metadata)
                _, message = self.call(create_table, metadata, "users", columns)
                self.assertEqual(metadata, original)
                self.assertIn("Ошибка валидации:", message)

    def test_explicit_id_is_first_and_not_duplicated(self):
        columns = ["name:str", "ID:int", "age:int"]
        result, _ = self.call(create_table, {}, "users", columns)
        self.assertEqual(result["users"], ["ID:int", "name:str", "age:int"])
        self.assertEqual(columns, ["name:str", "ID:int", "age:int"])

    def test_invalid_table_name(self):
        result, message = self.call(create_table, {}, "bad-name", ["name:str"])
        self.assertIsNone(result)
        self.assertIn("Ошибка валидации:", message)

    def test_drop_missing_keeps_other_tables(self):
        metadata = {"users": ["ID:int"]}
        result, message = self.call(drop_table, metadata, "products")
        self.assertIsNone(result)
        self.assertEqual(metadata, {"users": ["ID:int"]})
        self.assertIn("Таблица или столбец 'products' не найден.", message)


class StorageTests(unittest.TestCase):
    def test_missing_and_unicode_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db_meta.json"
            self.assertEqual(load_metadata(path), {})
            data = {"пользователи": ["ID:int", "имя:str"]}
            save_metadata(path, data)
            self.assertEqual(load_metadata(path), data)
            self.assertIn("пользователи", path.read_text(encoding="utf-8"))

    def test_broken_json_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db_meta.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_metadata(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


class CommandTests(unittest.TestCase):
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

    def test_full_session_and_persistence_across_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            first = self.session(
                folder,
                [
                    "create_table users name:str age:int is_active:bool",
                    "create_table users name:str",
                    "list_tables",
                    "exit",
                ],
            )
            self.assertIn("ID:int, name:str, age:int, is_active:bool", first)
            self.assertIn('Таблица "users" уже существует.', first)
            self.assertIn("- users", first)
            second = self.session(
                folder,
                [
                    "list_tables",
                    "drop_table users",
                    "y",
                    "drop_table products",
                    "y",
                    "exit",
                ],
            )
            self.assertIn("- users", second)
            self.assertIn('Таблица "users" успешно удалена.', second)
            self.assertIn("Таблица или столбец 'products' не найден.", second)
            self.assertEqual(load_metadata(Path(folder) / "db_meta.json"), {})

    def test_bad_commands_then_valid_quoted_command(self):
        with tempfile.TemporaryDirectory() as folder:
            output = self.session(
                folder,
                [
                    "unknown argument",
                    "create_table",
                    "create_table users",
                    "drop_table",
                    "drop_table users extra",
                    "list_tables extra",
                    "exit extra",
                    'create_table "unclosed',
                    "create_table invalid name:float",
                    'create_table "users" "name:str"',
                    "help",
                    "exit",
                ],
            )
            self.assertIn("Функции unknown нет. Попробуйте снова.", output)
            self.assertGreaterEqual(
                output.count("Ошибка валидации:")
                + output.count("Некорректное значение:"),
                8,
            )
            self.assertEqual(
                load_metadata(Path(folder) / "db_meta.json"),
                {"users": ["ID:int", "name:str"]},
            )

    def test_read_only_and_failed_operations_do_not_create_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = self.session(
                folder,
                [
                    "list_tables",
                    "drop_table missing",
                    "y",
                    "create_table t age:float",
                    "exit",
                ],
            )
            self.assertIn("Таблиц пока нет.", output)
            self.assertFalse((Path(folder) / "db_meta.json").exists())

    def test_broken_metadata_is_preserved(self):
        for content in ("{broken", "[]"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "db_meta.json"
                path.write_text(content, encoding="utf-8")
                output = self.session(folder, ["exit"])
                self.assertIn("Ошибка", output)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_eof_exits(self):
        with tempfile.TemporaryDirectory() as folder:
            self.session(folder, [])

    def test_only_successful_mutations_are_saved(self):
        metadata = {}
        commands = [
            "create_table users name:str",
            "create_table users age:int",
            "create_table bad name:float",
            "help",
            "list_tables",
            "drop_table missing",
            "drop_table users",
            "exit",
        ]
        saved = []
        with (
            patch("primitive_db.engine.load_metadata", return_value=metadata),
            patch("primitive_db.engine.prompt.string", side_effect=commands),
            patch("builtins.input", return_value="y"),
            patch("primitive_db.engine.save_table_data"),
            patch("primitive_db.engine.remove_table_data"),
            patch(
                "primitive_db.engine.save_metadata",
                side_effect=lambda _, data: saved.append(copy.deepcopy(data)),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            run()
        self.assertEqual(saved, [{"users": ["ID:int", "name:str"]}, {}])


if __name__ == "__main__":
    unittest.main()
