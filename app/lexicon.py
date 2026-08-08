from __future__ import annotations

import hashlib
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

from app.domain import Language, MeaningFrequency, POS, WordMeaning
from app.repositories.base import Repository


KOREAN_LEXICON_SOURCE = "Korean Basic Dictionary"
KOREAN_LEXICON_VERSION = "2026-07"
KOREAN_LEXICON_URL = "https://krdict.korean.go.kr/dicBatchDownload?seq=211"
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


class LexiconManager:
    def ensure_installed(
        self, repository: Repository, language: Language
    ) -> None:
        if language is not Language.KOREAN:
            raise ValueError(
                f"Word meanings are not available for {language.value} documents"
            )
        if repository.get_lexicon_version(KOREAN_LEXICON_SOURCE) is not None:
            return

        with TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "korean-basic-dictionary.zip"
            request = Request(KOREAN_LEXICON_URL, headers={"User-Agent": "Luculent"})
            with urlopen(request, timeout=60) as response:
                with archive_path.open("wb") as archive_file:
                    copyfileobj(response, archive_file)
            if _sha256(archive_path) != KOREAN_LEXICON_SHA256:
                raise ValueError("Downloaded Korean lexicon failed verification")
            repository.install_lexicon(
                KOREAN_LEXICON_SOURCE,
                KOREAN_LEXICON_VERSION,
                KOREAN_LEXICON_SHA256,
                _iter_korean_meanings(archive_path),
            )


def ensure_lexicon(repository: Repository, language: Language) -> None:
    LexiconManager().ensure_installed(repository, language)


def _iter_korean_meanings(
    archive_path: Path,
) -> Iterator[tuple[str, Language, POS, WordMeaning]]:
    display_orders: defaultdict[tuple[str, POS], int] = defaultdict(int)
    with zipfile.ZipFile(archive_path) as archive:
        for filename in archive.namelist():
            data = json.loads(archive.read(filename))
            entries = data["LexicalResource"]["Lexicon"]["LexicalEntry"]
            for entry in entries:
                lemma = _feature(entry.get("Lemma", {}), "writtenForm")
                pos = _KOREAN_POS.get(_feature(entry, "partOfSpeech"))
                if not lemma or pos is None:
                    continue
                lemma = lemma.casefold()
                identity = (lemma, pos)
                for sense in _items(entry.get("Sense")):
                    english = next(
                        (
                            equivalent
                            for equivalent in _items(sense.get("Equivalent"))
                            if _feature(equivalent, "language") == "영어"
                        ),
                        None,
                    )
                    yield (
                        lemma,
                        Language.KOREAN,
                        pos,
                        WordMeaning(
                            None,
                            korean_definition=_feature(sense, "definition") or "",
                            english_definition=(
                                ""
                                if english is None
                                else _feature(english, "definition") or ""
                            ),
                            gloss=(
                                ""
                                if english is None
                                else _feature(english, "lemma") or ""
                            ),
                            frequency=MeaningFrequency.COMMON,
                            display_order=display_orders[identity],
                        ),
                    )
                    display_orders[identity] += 1


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
