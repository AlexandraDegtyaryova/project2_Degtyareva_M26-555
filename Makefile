.PHONY: install run lint format test build check

install:
	uv sync --frozen

run:
	uv run database

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run python tests/run_tests.py

build:
	uv build

check: lint test build
	uvx twine check dist/*
