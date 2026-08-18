from __future__ import annotations

import os
from pathlib import Path

from tinydb import TinyDB
from tinydb.table import Table

_ENV_DB_PATH = "SUPPLIERS_DB_PATH"
_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "suppliers.json"

_db_instance: TinyDB | None = None
_db_path: Path | None = None


def resolve_db_path() -> Path:
    configured_path = os.getenv(_ENV_DB_PATH)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return _DEFAULT_DB_PATH


def get_db() -> TinyDB:
    global _db_instance, _db_path

    path = resolve_db_path()
    if _db_instance is None or _db_path != path:
        close_db()
        path.parent.mkdir(parents=True, exist_ok=True)
        _db_instance = TinyDB(path)
        _db_path = path
    return _db_instance


def get_suppliers_table() -> Table:
    return get_db().table("suppliers")


def close_db() -> None:
    global _db_instance, _db_path
    if _db_instance is not None:
        _db_instance.close()
        _db_instance = None
        _db_path = None
