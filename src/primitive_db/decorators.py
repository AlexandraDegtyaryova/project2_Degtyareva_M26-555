"""Общие обёртки операций БД и замыкание для кэширования."""

import time
from functools import wraps


def handle_db_errors(func):
    """Показать ошибку операции; None означает, что результата нет."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            print(
                "Ошибка: Файл данных не найден. "
                "Возможно, база данных не инициализирована."
            )
        except KeyError as error:
            print(f"Ошибка: Таблица или столбец {error} не найден.")
        except ValueError as error:
            print(f"Ошибка валидации: {error}")
        except OSError as error:
            print(f"Ошибка работы с файлом: {error}")
        except Exception as error:
            print(f"Произошла непредвиденная ошибка: {error}")
        return None

    return wrapper


def confirm_action(action_name):
    """Фабрика декораторов: выполнять опасную операцию только после y."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                answer = input(
                    f'Вы уверены, что хотите выполнить "{action_name}"? [y/n]: '
                )
            except (EOFError, KeyboardInterrupt):
                answer = ""
                print()
            if answer != "y":
                print(f'Операция "{action_name}" отменена.')
                return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def log_time(func):
    """Измерять длительность монотонными часами, сохраняя результат вызова."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.monotonic() - started
            print(f"Функция {func.__name__} выполнилась за {elapsed:.3f} секунд")

    return wrapper


def create_cacher():
    """Вернуть функцию, которая запоминает результаты в словаре замыкания."""
    cache = {}

    def cache_result(key, value_func):
        if key not in cache:
            cache[key] = value_func()
        return cache[key]

    return cache_result
