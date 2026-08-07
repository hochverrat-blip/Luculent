from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from shutil import copyfileobj
from urllib.request import Request, urlopen

from app.domain import Language, MeaningFrequency, POS, WordMeaning


KOREAN_LEXICON_VERSION = "2026-07"
KOREAN_LEXICON_URL = "https://krdict.korean.go.kr/dicBatchDownload?seq=211"
KOREAN_LEXICON_DOWNLOAD_BYTES = 84_442_933
KOREAN_LEXICON_SHA256 = (
    "13ff666e78363e3abc73cdb2e582a6776ddfa7a120f18c0b79bd03fa56d860f9"
)

_KOREAN_POS = {
    "고유 명사": POS.NOUN,
    "대명사": POS.NOUN,
    "동사": POS.VERB,
    "명사": POS.NOUN,
    "부사": POS.ADVERB,
    "의존 명사": POS.NOUN,
    "형용사": POS.ADJECTIVE,
}


class Lexicon(ABC):
    @abstractmethod
    def get_meanings(
        self, lemma: str, language: Language, pos: POS
    ) -> list[WordMeaning]:
        """Return meanings in display order"""

    def close(self) -> None:
        pass


class KoreanLexicon(Lexicon):
    def __init__(self, database_path: str | Path):
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row

    def get_meanings(
        self, lemma: str, language: Language, pos: POS
    ) -> list[WordMeaning]:
        if language is not Language.KOREAN:
            return []
        rows = self._connection.execute(
            """
            SELECT korean_definition, english_definition, gloss
            FROM meanings
            WHERE lemma = ? AND pos = ?
            ORDER BY meaning_id
            """,
            (lemma, pos.name),
        ).fetchall()
        return [
            WordMeaning(
                None,
                korean_definition=row["korean_definition"],
                english_definition=row["english_definition"],
                gloss=row["gloss"],
                frequency=MeaningFrequency.COMMON,
                display_order=index,
            )
            for index, row in enumerate(rows)
        ]

    def close(self) -> None:
        self._connection.close()


class LexiconManager:
    def __init__(self, data_directory: str | Path | None = None):
        self._data_directory = (
            Path(data_directory) if data_directory is not None else _data_directory()
        )

    def get_lexicon(self, language: Language) -> Lexicon:
        if language is not Language.KOREAN:
            raise ValueError(
                f"Word meanings are not available for {language.value} documents"
            )
        database_path = self._data_directory / (
            f"korean-basic-dictionary-{KOREAN_LEXICON_VERSION}.db"
        )
        if not database_path.exists():
            self._install_korean_lexicon(database_path)
        return KoreanLexicon(database_path)

    def _install_korean_lexicon(self, database_path: Path) -> None:
        self._data_directory.mkdir(parents=True, exist_ok=True)
        archive_path = database_path.with_suffix(".zip.download")
        building_path = database_path.with_suffix(".db.building")
        try:
            request = Request(KOREAN_LEXICON_URL, headers={"User-Agent": "Luculent"})
            with urlopen(request, timeout=60) as response:
                with archive_path.open("wb") as archive_file:
                    copyfileobj(response, archive_file)
            if _sha256(archive_path) != KOREAN_LEXICON_SHA256:
                raise ValueError("Downloaded Korean lexicon failed verification")
            _convert_korean_lexicon(archive_path, building_path)
            building_path.replace(database_path)
        finally:
            archive_path.unlink(missing_ok=True)
            building_path.unlink(missing_ok=True)


def create_lexicon(language: Language) -> Lexicon:
    return LexiconManager().get_lexicon(language)


def _convert_korean_lexicon(archive_path: Path, database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE meanings (
                meaning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lemma TEXT NOT NULL,
                pos TEXT NOT NULL,
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss TEXT NOT NULL
            );
            CREATE INDEX meanings_lookup ON meanings (lemma, pos);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        with zipfile.ZipFile(archive_path) as archive:
            for filename in archive.namelist():
                data = json.loads(archive.read(filename))
                entries = data["LexicalResource"]["Lexicon"]["LexicalEntry"]
                for entry in entries:
                    _insert_entry(connection, entry)
        connection.execute(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            ("version", KOREAN_LEXICON_VERSION),
        )
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            (
                ("source_url", KOREAN_LEXICON_URL),
                ("source_sha256", KOREAN_LEXICON_SHA256),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _insert_entry(connection: sqlite3.Connection, entry: dict) -> None:
    lemma = _feature(entry.get("Lemma", {}), "writtenForm")
    pos = _KOREAN_POS.get(_feature(entry, "partOfSpeech"))
    if not lemma or pos is None:
        return
    for sense in _items(entry.get("Sense")):
        korean_definition = _feature(sense, "definition") or ""
        english = next(
            (
                equivalent
                for equivalent in _items(sense.get("Equivalent"))
                if _feature(equivalent, "language") == "영어"
            ),
            None,
        )
        connection.execute(
            """
            INSERT INTO meanings (
                lemma, pos, korean_definition, english_definition, gloss
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                lemma.casefold(),
                pos.name,
                korean_definition,
                "" if english is None else _feature(english, "definition") or "",
                "" if english is None else _feature(english, "lemma") or "",
            ),
        )


def _feature(value: dict | list, attribute: str) -> str | None:
    for item in _features(value):
        if item.get("att") == attribute:
            return item.get("val")
    return None


def _features(value: dict | list) -> list[dict]:
    if isinstance(value, list):
        return [feature for item in value for feature in _features(item)]
    features = value.get("feat", [])
    return [features] if isinstance(features, dict) else features


def _items(value: object) -> list[dict]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _data_directory() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "Luculent" / "dictionaries"
