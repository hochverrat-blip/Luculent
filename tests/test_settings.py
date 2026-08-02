from pathlib import Path

import pytest

import app.settings as settings_module
from app.repositories import SQLiteRepository, create_repository
from app.settings import Settings


def test_settings_load_key_value_file(tmp_path):
    settings_file = tmp_path / "settings.txt"
    settings_file.write_text(
        """
        # Select the database adapter
        database = mysql
        mysql_host = database.example
        mysql_port = 3308
        mysql_database = luculent_test
        mysql_user = tester
        mysql_password = secret=value
        """,
        encoding="utf-8",
    )

    settings = Settings.from_file(settings_file)

    assert settings.database == "mysql"
    assert settings.mysql_host == "database.example"
    assert settings.mysql_port == 3308
    assert settings.mysql_database == "luculent_test"
    assert settings.mysql_user == "tester"
    assert settings.mysql_password == "secret=value"


def test_settings_reject_unknown_keys(tmp_path):
    settings_file = tmp_path / "settings.txt"
    settings_file.write_text("databsae=mysql", encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown setting"):
        Settings.from_file(settings_file)


@pytest.mark.parametrize(
    "contents, expected_message",
    [
        ("database", "expected key=value"),
        ("database=postgres", "database must be either sqlite or mysql"),
        ("mysql_port=not-a-number", "mysql_port must be an integer"),
    ],
)
def test_settings_reject_invalid_values(tmp_path, contents, expected_message):
    settings_file = tmp_path / "settings.txt"
    settings_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        Settings.from_file(settings_file)


def test_missing_settings_can_use_sqlite_defaults(tmp_path):
    settings = Settings.from_file(
        tmp_path / "missing.txt", use_defaults_when_missing=True
    )

    assert settings == Settings()


def test_missing_settings_are_created_from_example_file(tmp_path):
    settings_file = tmp_path / "settings.txt"
    example_file = tmp_path / "settings.example.txt"
    example_contents = "database=sqlite\nsqlite_path=created.db\n"
    example_file.write_text(example_contents, encoding="utf-8")

    settings = Settings.from_file(settings_file)

    assert settings_file.read_text(encoding="utf-8") == example_contents
    assert settings.database == "sqlite"
    assert settings.sqlite_path == "created.db"


def test_default_settings_path_is_stable_when_working_directory_changes(
    tmp_path, monkeypatch
):
    project_directory = tmp_path / "project"
    project_directory.mkdir()
    settings_file = project_directory / "settings.txt"
    example_file = project_directory / "settings.example.txt"
    example_file.write_text("database=sqlite\nsqlite_path=stable.db\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_file)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    settings = Settings.from_file()

    assert settings_file.exists()
    assert settings.sqlite_path == "stable.db"


def test_factory_selects_sqlite_from_settings(tmp_path):
    settings = Settings(database="sqlite", sqlite_path=str(tmp_path / "test.db"))

    repository = create_repository(settings)
    try:
        assert isinstance(repository, SQLiteRepository)
    finally:
        repository.close()


def test_factory_loads_backend_from_settings_file(tmp_path):
    database_path = tmp_path / "from-settings.db"
    settings_file = tmp_path / "settings.txt"
    settings_file.write_text(
        f"database=sqlite\nsqlite_path={database_path}\n",
        encoding="utf-8",
    )

    repository = create_repository(settings_path=str(settings_file))
    try:
        assert isinstance(repository, SQLiteRepository)
        assert database_path.exists()
    finally:
        repository.close()
