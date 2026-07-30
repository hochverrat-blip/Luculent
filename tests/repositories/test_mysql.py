import os

import pytest

from app.domain.document import Document
from app.domain.enums import Language
from app.repositories import MySQLRepository
from app.settings import Settings
from tests.repositories.contract import RepositoryContract


@pytest.fixture
def repository():
    settings = Settings(
        database="mysql",
        mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("MYSQL_PORT", "32000")),
        mysql_database=os.getenv("MYSQL_DATABASE", "luculent"),
        mysql_user=os.getenv("MYSQL_USER", "luculent"),
        mysql_password=os.getenv("MYSQL_PASSWORD", "luculent"),
    )
    try:
        from mysql.connector import Error as MySQLError
    except ImportError:
        pytest.skip("mysql-connector-python is not installed")

    try:
        repo = MySQLRepository(settings)
    except MySQLError as error:
        if error.errno in {2002, 2003, 2005}:
            pytest.skip("MySQL test server is not available, skipping MySQL tests")
        raise

    try:
        repo.initialize()
        yield repo
    finally:
        repo.close()


class TestMySQLRepository(RepositoryContract):
    repository_class = MySQLRepository


def test_mysql_repository_uses_connection_settings():
    captured = {}

    class FakeConnection:
        def close(self):
            pass

    def connect(**arguments):
        captured.update(arguments)
        return FakeConnection()

    settings = Settings(
        database="mysql",
        mysql_host="mysql.example",
        mysql_port=3308,
        mysql_database="luculent_test",
        mysql_user="tester",
        mysql_password="secret",
    )

    repository = MySQLRepository(settings, connect=connect)
    repository.close()

    assert captured == {
        "host": "mysql.example",
        "port": 3308,
        "database": "luculent_test",
        "user": "tester",
        "password": "secret",
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }


def test_mysql_foreign_keys_prevent_orphaned_documents(repository):
    from mysql.connector import IntegrityError

    with pytest.raises(IntegrityError):
        repository.save_document(
            2147483000,
            Document(None, "Title", "Text", Language.ENGLISH),
        )


def test_mysql_uses_auto_increment_for_entity_tables(repository):
    rows = repository._fetch_all(
        """
        SELECT TABLE_NAME, EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('users', 'documents', 'doc_parts', 'words')
          AND COLUMN_KEY = 'PRI'
        ORDER BY TABLE_NAME
        """,
        (),
    )

    assert len(rows) == 4
    assert all("auto_increment" in row["EXTRA"] for row in rows)
