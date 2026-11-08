import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primitive_db.core import delete, insert, select, update, validate_fields
from primitive_db.parser import (
    parse_data_command,
    parse_set_clause,
    parse_values,
    parse_where_clause,
)
from primitive_db.utils import load_table_data, save_table_data

SCHEMA = {"users": ["ID:int", "name:str", "age:int", "is_active:bool"]}


class ParserTests(unittest.TestCase):
    def test_literals_and_quoted_separators(self):
        self.assertEqual(
            parse_values('("Doe, Jane = where", -28, false)'),
            ["Doe, Jane = where", -28, False],
        )
        self.assertEqual(parse_values("('Ира', +28, true)"), ["Ира", 28, True])
        self.assertEqual(parse_values('( "", 0, false )'), ["", 0, False])
        self.assertEqual(parse_values("()"), [])
        self.assertEqual(parse_values(r'("A\"B", 1, true)')[0], 'A"B')

    def test_where_and_multiple_set(self):
        self.assertEqual(parse_where_clause("age=28"), {"age": 28})
        self.assertEqual(
            parse_set_clause('name="where, set", age = 29, is_active=false'),
            {"name": "where, set", "age": 29, "is_active": False},
        )
        parsed = parse_data_command(
            'update users set where="where", age=29 where name="Ира"'
        )
        self.assertEqual(parsed["set"], {"where": "where", "age": 29})
        self.assertEqual(parsed["where"], {"name": "Ира"})

    def test_all_command_forms(self):
        examples = {
            'insert into users values ("Sergei",28,true)': "insert",
            "select from users": "select",
            "SELECT FROM users WHERE age=28": "select",
            'update users set age=29 where name="Sergei"': "update",
            "delete from users where ID=1": "delete",
            "info users": "info",
        }
        for text, command in examples.items():
            with self.subTest(text=text):
                parsed = parse_data_command(text)
                self.assertEqual(parsed["command"], command)
                self.assertEqual(parsed["table_name"], "users")

    def test_malformed_values_rejected(self):
        for text in (
            "(Sergei, 28, true)",
            '("Sergei", 28, true,)',
            '("Sergei" 28, true)',
            '("Sergei", 2.8, true)',
            '("Sergei", null, true)',
            '("unclosed, 28, true)',
            '("Sergei", 28, true) extra',
            '"Sergei", 28, true',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_values(text)

    def test_unsafe_or_incomplete_commands_rejected(self):
        for text in (
            "delete from users",
            "update users set age=29",
            "select from users where",
            "select from users where age>28",
            "select from users where age=28 extra",
            "update users set age=29,age=30 where ID=1",
            "info users extra",
            "insert users values (1)",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_data_command(text)


class CoreCrudTests(unittest.TestCase):
    def setUp(self):
        self.data = [
            {"ID": 1, "name": "Sergei", "age": 28, "is_active": True},
            {"ID": 3, "name": "Anna", "age": 28, "is_active": False},
        ]

    def test_insert_generates_max_id_without_mutating_loaded_data(self):
        original = copy.deepcopy(self.data)
        with patch("primitive_db.core.load_table_data", return_value=self.data):
            result = insert(SCHEMA, "users", ["Ира", 30, False])
        self.assertEqual(result[-1]["ID"], 4)
        self.assertEqual(self.data, original)

    def test_first_insert_and_required_fields(self):
        with patch("primitive_db.core.load_table_data", return_value=[]):
            self.assertEqual(insert(SCHEMA, "users", ["", 0, False])[-1]["ID"], 1)
            for values in (["A", 28], [1, "A", 28, True], ["A", True, True]):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    insert(SCHEMA, "users", values)
        with self.assertRaises(ValueError):
            insert(SCHEMA, "missing", ["A", 28, True])

    def test_select_update_delete_all_matching_rows(self):
        original = copy.deepcopy(self.data)
        self.assertEqual(select(self.data), self.data)
        self.assertEqual(len(select(self.data, {"age": 28})), 2)
        self.assertEqual(select(self.data, {"ID": True}), [])
        changed = update(self.data, {"age": 29, "is_active": True}, {"age": 28})
        self.assertTrue(all(row["age"] == 29 for row in changed))
        self.assertEqual(delete(self.data, {"age": 28}), [])
        self.assertEqual(self.data, original)

    def test_types_and_id_are_checked(self):
        schema = {"ID": "int", "name": "str", "age": "int", "is_active": "bool"}
        for fields in ({"age": True}, {"is_active": 1}, {"name": 28}, {"other": 1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_fields(schema, fields)
        with self.assertRaises(ValueError):
            update(self.data, {"ID": 3}, {"ID": 1})

    def test_duplicate_saved_ids_are_rejected(self):
        broken = [self.data[0], dict(self.data[0])]
        with (
            patch("primitive_db.core.load_table_data", return_value=broken),
            self.assertRaises(ValueError),
        ):
            insert(SCHEMA, "users", ["Ира", 30, True])


class CrudSessionTests(unittest.TestCase):
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

    def create(self, folder):
        return self.session(
            folder,
            [
                "create_table users name:str age:int is_active:bool",
                'insert into users values ("Sergei", 28, true)',
                'insert into users values ("Ира, where", 28, false)',
                "exit",
            ],
        )

    def test_full_crud_persists_across_restarts_and_prints_table(self):
        with tempfile.TemporaryDirectory() as folder:
            first = self.create(folder)
            self.assertIn("ID=1 успешно добавлена", first)
            self.assertIn("ID=2 успешно добавлена", first)
            second = self.session(
                folder,
                [
                    "select from users where age = 28",
                    'update users set age=29, is_active=false where name="Sergei"',
                    "info users",
                    "exit",
                ],
            )
            self.assertIn("+----+", second)
            self.assertIn("Sergei", second)
            self.assertIn("ID=1 в таблице", second)
            self.assertIn("Количество записей: 2", second)
            path = Path(folder) / "data" / "users.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["age"], 29)
            self.assertIs(data[0]["is_active"], False)
            third = self.session(
                folder,
                ["delete from users where ID=1", "select from users", "exit"],
            )
            self.assertIn("ID=1 успешно удалена", third)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([row["ID"] for row in data], [2])

    def test_invalid_changes_leave_saved_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            self.create(folder)
            path = Path(folder) / "data" / "users.json"
            original = path.read_bytes()
            output = self.session(
                folder,
                [
                    'insert into users values ("A", true, true)',
                    'insert into users values (1, "A", 28, true)',
                    'update users set age="29" where ID=1',
                    "update users set ID=9 where ID=1",
                    "update users set unknown=9 where ID=1",
                    "delete from users where unknown=1",
                    "delete from users where ID=true",
                    "delete from users",
                    "select from missing",
                    "exit",
                ],
            )
            self.assertGreaterEqual(output.count("Некорректное значение:"), 8)
            self.assertIn('Таблица "missing" не существует', output)
            self.assertEqual(path.read_bytes(), original)

    def test_deletion_gaps_do_not_duplicate_remaining_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            self.create(folder)
            self.session(
                folder,
                [
                    "delete from users where ID=1",
                    'insert into users values ("A", 30, true)',
                    "exit",
                ],
            )
            path = Path(folder) / "data" / "users.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([row["ID"] for row in data], [2, 3])

    def test_drop_and_recreate_does_not_restore_old_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            self.create(folder)
            self.session(folder, ["drop_table users", "exit"])
            self.assertFalse((Path(folder) / "data" / "users.json").exists())
            output = self.session(
                folder,
                ["create_table users title:str", "info users", "exit"],
            )
            self.assertIn("Количество записей: 0", output)

    def test_broken_data_is_preserved_and_loop_survives(self):
        for content in ("{broken", "{}", '[{"ID": 1}]'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                self.create(folder)
                path = Path(folder) / "data" / "users.json"
                path.write_text(content, encoding="utf-8")
                output = self.session(
                    folder,
                    ['insert into users values ("A", 28, true)', "help", "exit"],
                )
                self.assertIn("help - справочная", output)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_empty_selection_and_no_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            self.session(folder, ["create_table users name:str", "exit"])
            output = self.session(
                folder,
                [
                    "select from users",
                    'update users set name="A" where ID=99',
                    "delete from users where ID=99",
                    "info users",
                    "exit",
                ],
            )
            self.assertIn("| ID |", output)
            self.assertEqual(output.count("Подходящих записей не найдено."), 2)
            self.assertIn("Количество записей: 0", output)


class TableStorageTests(unittest.TestCase):
    def test_storage_creates_folder_and_preserves_unicode(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("primitive_db.utils.table_filepath") as filepath:
                path = Path(folder) / "data" / "users.json"
                filepath.return_value = path
                self.assertEqual(load_table_data("users"), [])
                data = [{"ID": 1, "name": "Ира"}]
                save_table_data("users", data)
                self.assertEqual(load_table_data("users"), data)
                self.assertIn("Ира", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
