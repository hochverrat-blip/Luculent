from pathlib import Path

from app.repositories.base import Repository
from app.repositories.sqlite import SQLiteRepository
from app.repositories.mysql import MySQLRepository
from app.settings import Settings


def create_repository(
    settings: Settings | None = None,
    *,
    settings_path: str | Path | None = None,
) -> Repository:
    selected = settings or Settings.from_file(
        settings_path, use_defaults_when_missing=True
    )
    if selected.database == "sqlite":
        repository: Repository = SQLiteRepository(selected.sqlite_path)
    elif selected.database == "mysql":
        repository: Repository = MySQLRepository(selected)
    else:
        raise ValueError(f"Unsupported database: {selected.database}")
    repository.initialize()
    return repository
