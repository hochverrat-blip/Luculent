import sqlite3

import pytest

from app.domain.document import Document
from app.domain.enums import Language
from app.domain.user import User
from app.repositories import SQLiteRepository, create_repository
from app.settings import Settings
from tests.repositories.contract import RepositoryContract


@pytest.fixture
def repository(tmp_path):
    with SQLiteRepository(tmp_path / "luculent-test.db") as repo:
        yield repo


class TestSQLiteRepository(RepositoryContract):
    repository_class = SQLiteRepository


def test_default_factory_creates_initialized_sqlite_repository(tmp_path):
    repository = create_repository(
        Settings(
            database="sqlite",
            sqlite_path=str(tmp_path / "factory-test.db"),
        )
    )
    try:
        user = User(None, "Vance")
        repository.save_user(user)
        assert repository.get_user(user.user_id).name == "Vance"
    finally:
        repository.close()


def test_sqlite_foreign_keys_prevent_orphaned_documents(repository):
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_document(
            2147483000,
            Document(None, "Title", "Text", Language.ENGLISH),
        )


def test_sqlite_uses_autoincrement_for_entity_tables(repository):
    rows = repository._connection.execute(
        "SELECT name FROM sqlite_sequence ORDER BY name"
    ).fetchall()

    assert rows == []
    repository.save_user(User(None, "Vance"))
    rows = repository._connection.execute(
        "SELECT name FROM sqlite_sequence ORDER BY name"
    ).fetchall()
    assert [row["name"] for row in rows] == ["users"]
