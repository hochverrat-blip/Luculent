from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from shutil import copyfile


@dataclass(frozen=True)
class Settings:
    database: str = "sqlite"
    sqlite_path: str = "luculent.db"
    mysql_host: str = "localhost"
    mysql_port: int = 32000
    mysql_database: str = "luculent"
    mysql_user: str = "luculent"
    mysql_password: str = "luculent"

    @classmethod
    def from_file(
        cls,
        path: str | Path = "settings.txt",
        *,
        use_defaults_when_missing: bool = False,
    ) -> Settings:
        settings_path = Path(path)
        if not settings_path.exists():
            example_path = settings_path.with_name("settings.example.txt")
            if example_path.exists():
                copyfile(example_path, settings_path)
            elif use_defaults_when_missing:
                return cls()
            else:
                raise FileNotFoundError(f"Settings file not found: {settings_path}")

        values: dict[str, str] = {}
        valid_keys = {field.name for field in fields(cls)}
        for line_number, raw_line in enumerate(
            settings_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(
                    f"Invalid settings line {line_number}: expected key=value"
                )
            key, value = (part.strip() for part in line.split("=", 1))
            if key not in valid_keys:
                raise ValueError(f"Unknown setting on line {line_number}: {key}")
            if not key or not value:
                raise ValueError(
                    f"Invalid settings line {line_number}: key and value are required"
                )
            values[key] = value

        if "mysql_port" in values:
            try:
                values["mysql_port"] = int(values["mysql_port"])
            except ValueError as error:
                raise ValueError("mysql_port must be an integer") from error

        settings = cls(**values)
        backend = settings.database.lower()
        if backend not in {"sqlite", "mysql"}:
            raise ValueError("database must be either sqlite or mysql")
        return cls(
            **{
                field.name: (
                    backend if field.name == "database" else getattr(settings, field.name)
                )
                for field in fields(cls)
            }
        )
