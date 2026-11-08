"""Общие настройки хранения, типов и команд приложения."""

META_FILE = "db_meta.json"
DATA_DIR = "data"
ID_COLUMN = "ID"
VALID_TYPES = {"int", "str", "bool"}
PYTHON_TYPES = {"int": int, "str": str, "bool": bool}
DATA_COMMANDS = {"insert", "select", "update", "delete", "info"}
TABLE_COMMANDS = {"create_table", "drop_table", "list_tables", "help", "exit"}
VALUE_SEPARATOR = ","
ASSIGNMENT_TOKEN_COUNT = 3
ASSIGNMENT_GROUP_SIZE = 4
MIN_INSERT_TOKEN_COUNT = 6
MIN_UPDATE_TOKEN_COUNT = 10
SINGLE_QUOTE_ESCAPES = {
    "\\": "\\",
    "'": "'",
    '"': '"',
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
