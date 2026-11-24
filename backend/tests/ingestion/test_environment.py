"""Verify Python 3.12 containerized ingestion runtime and core dependencies."""

import importlib
import sys


def test_python_version_is_3_12() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_required_ingestion_packages_importable() -> None:
    modules = [
        "sqlalchemy",
        "psycopg",
        "alembic",
        "httpx",
        "bs4",
        "lxml",
        "pdfplumber",
        "docx",
        "openpyxl",
        "pydantic_settings",
        "apscheduler",
        "respx",
    ]
    for name in modules:
        assert importlib.import_module(name) is not None
