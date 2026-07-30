from pathlib import Path

from app.repositories.base import Repository
from app.repositories.sqlite import SQLiteRepository


def create_repository(database_path: str | Path = "luculent.db") -> Repository:
    """Create and initialize the application's default repository."""
    repository = SQLiteRepository(database_path)
    repository.initialize()
    return repository
