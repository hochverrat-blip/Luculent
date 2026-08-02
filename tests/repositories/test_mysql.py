import os

import pytest

from app.domain.document import Document
from app.domain.enums import Language
from app.repositories import MySQLRepository
from app.settings import Settings
from tests.repositories.contract import RepositoryContract


@pytest.fixture
def repository():
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("MYSQL_PORT", "32000"))
    root_password = os.getenv("MYSQL_ROOT_PASSWORD", "root")
    running_in_ci = os.getenv("GITHUB_ACTIONS") == "true"
    try:
        from mysql.connector import connect
        from mysql.connector import Error as MySQLError
    except ImportError:
        if running_in_ci:
            raise
        pytest.skip("mysql-connector-python is not installed")

    try:
        admin_connection = connect(
            host=host,
            port=port,
            user="root",
            password=root_password,
        )
    except MySQLError as error:
        if not running_in_ci and error.errno in {2002, 2003, 2005}:
            pytest.skip("MySQL test server is not available, skipping MySQL tests")
        raise

    cursor = admin_connection.cursor()
    try:
        cursor.execute("DROP DATABASE IF EXISTS luculent_test")
        cursor.execute(
            "CREATE DATABASE luculent_test "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.close()

        settings = Settings(
            database="mysql",
            mysql_host=host,
            mysql_port=port,
            mysql_database="luculent_test",
            mysql_user="root",
            mysql_password=root_password,
        )
        repo = MySQLRepository(settings)
        repo.initialize()
        yield repo
    finally:
        if "repo" in locals():
            repo.close()
        cleanup_cursor = admin_connection.cursor()
        cleanup_cursor.execute("DROP DATABASE IF EXISTS luculent_test")
        cleanup_cursor.close()
        admin_connection.close()


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
