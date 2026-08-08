import hashlib
import io
import json
import zipfile

import pytest

import app.lexicon as lexicon_module
from app.domain import Language, POS, User, Word
from app.lexicon import KOREAN_LEXICON_SOURCE, KOREAN_LEXICON_VERSION, LexiconManager
from app.repositories.sqlite import SQLiteRepository


def _feature(att, val):
    return {"att": att, "val": val}


def _entry(lemma, pos, senses):
    return {
        "Lemma": {"feat": _feature("writtenForm", lemma)},
        "feat": [_feature("partOfSpeech", pos)],
        "Sense": [
            {
                "feat": _feature("definition", korean),
                "Equivalent": {
                    "feat": [
                        _feature("language", "영어"),
                        _feature("lemma", gloss),
                        _feature("definition", english),
                    ]
                },
            }
            for korean, english, gloss in senses
        ],
    }


def _archive_bytes():
    data = {
        "LexicalResource": {
            "Lexicon": {
                "LexicalEntry": [
                    _entry(
                        "배",
                        "명사",
                        [
                            ("사람의 몸통 가운데 부분.", "The abdomen.", "stomach"),
                            ("물 위로 다니는 운송 수단.", "A vessel.", "boat"),
                        ],
                    ),
                    _entry("배", "동사", [("두 배가 되다.", "To double.", "double")]),
                ]
            }
        }
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("1_2_test.json", json.dumps(data, ensure_ascii=False))
    return archive.getvalue()


@pytest.fixture
def repository(tmp_path):
    with SQLiteRepository(tmp_path / "main.db") as repository:
        yield repository


def _configure_download(monkeypatch, archive):
    downloads = {"count": 0}

    def open_archive(request, timeout):
        downloads["count"] += 1
        return io.BytesIO(archive)

    monkeypatch.setattr(lexicon_module, "urlopen", open_archive)
    monkeypatch.setattr(
        lexicon_module,
        "KOREAN_LEXICON_SHA256",
        hashlib.sha256(archive).hexdigest(),
    )
    return downloads


def test_manager_installs_shared_lexicon_once(repository, monkeypatch):
    archive = _archive_bytes()
    downloads = _configure_download(monkeypatch, archive)
    manager = LexiconManager()

    manager.ensure_installed(repository, Language.KOREAN)
    manager.ensure_installed(repository, Language.KOREAN)
    repository.save_user(User(1, "Reader"))
    word = Word(None, "배", Language.KOREAN, POS.NOUN)
    repository.save_word(1, word)
    meanings = repository.get_word(word.word_id).meanings

    assert downloads["count"] == 1
    assert repository.get_lexicon_version(KOREAN_LEXICON_SOURCE) == KOREAN_LEXICON_VERSION
    assert [meaning.gloss for meaning in meanings] == ["stomach", "boat"]
    assert meanings[0].korean_definition == "사람의 몸통 가운데 부분."
    assert meanings[0].english_definition == "The abdomen."
    assert [meaning.display_order for meaning in meanings] == [0, 1]
    assert all(isinstance(meaning.meaning_id, int) for meaning in meanings)


def test_manager_accepts_any_installed_lexicon_version(
    repository, monkeypatch
):
    repository.install_lexicon(
        KOREAN_LEXICON_SOURCE,
        "older-version",
        "older-checksum",
        [],
    )
    monkeypatch.setattr(
        lexicon_module,
        "urlopen",
        lambda request, timeout: pytest.fail("lexicon should not be downloaded"),
    )

    LexiconManager().ensure_installed(repository, Language.KOREAN)

    assert repository.get_lexicon_version(KOREAN_LEXICON_SOURCE) == "older-version"


def test_shared_lexicon_filters_by_part_of_speech(repository, monkeypatch):
    archive = _archive_bytes()
    _configure_download(monkeypatch, archive)
    LexiconManager().ensure_installed(repository, Language.KOREAN)
    repository.save_user(User(1, "Reader"))
    noun = Word(None, "배", Language.KOREAN, POS.NOUN)
    verb = Word(None, "배", Language.KOREAN, POS.VERB)
    missing = Word(None, "없는말", Language.KOREAN, POS.NOUN)
    repository.save_word(1, noun)
    repository.save_word(1, verb)
    repository.save_word(1, missing)

    assert [meaning.gloss for meaning in repository.get_word(verb.word_id).meanings] == [
        "double"
    ]
    assert repository.get_word(missing.word_id).meanings == []


def test_manager_rejects_languages_without_a_lexicon(repository):
    with pytest.raises(ValueError, match="not available for English documents"):
        LexiconManager().ensure_installed(repository, Language.ENGLISH)
