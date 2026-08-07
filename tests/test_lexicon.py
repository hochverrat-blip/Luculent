import hashlib
import io
import json
import zipfile

import pytest

import app.lexicon as lexicon_module
from app.domain import Language, POS
from app.lexicon import LexiconManager


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
                    _entry(
                        "배",
                        "동사",
                        [("두 배가 되다.", "To double.", "double")],
                    ),
                ]
            }
        }
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("1_2_test.json", json.dumps(data, ensure_ascii=False))
    return archive.getvalue()


def test_manager_installs_and_reuses_a_local_korean_lexicon(tmp_path, monkeypatch):
    archive = _archive_bytes()
    downloads = 0

    def open_archive(request, timeout):
        nonlocal downloads
        downloads += 1
        return io.BytesIO(archive)

    monkeypatch.setattr(lexicon_module, "urlopen", open_archive)
    monkeypatch.setattr(
        lexicon_module,
        "KOREAN_LEXICON_SHA256",
        hashlib.sha256(archive).hexdigest(),
    )
    manager = LexiconManager(tmp_path)

    lexicon = manager.get_lexicon(Language.KOREAN)
    meanings = lexicon.get_meanings("배", Language.KOREAN, POS.NOUN)
    lexicon.close()
    cached = manager.get_lexicon(Language.KOREAN)
    cached.close()

    assert downloads == 1
    assert [meaning.gloss for meaning in meanings] == ["stomach", "boat"]
    assert meanings[0].korean_definition == "사람의 몸통 가운데 부분."
    assert meanings[0].english_definition == "The abdomen."
    assert [meaning.display_order for meaning in meanings] == [0, 1]
    assert all(meaning.meaning_id is None for meaning in meanings)


def test_korean_lexicon_filters_by_part_of_speech(tmp_path, monkeypatch):
    archive = _archive_bytes()
    monkeypatch.setattr(
        lexicon_module,
        "urlopen",
        lambda request, timeout: io.BytesIO(archive),
    )
    monkeypatch.setattr(
        lexicon_module,
        "KOREAN_LEXICON_SHA256",
        hashlib.sha256(archive).hexdigest(),
    )
    lexicon = LexiconManager(tmp_path).get_lexicon(Language.KOREAN)

    assert [
        meaning.gloss
        for meaning in lexicon.get_meanings("배", Language.KOREAN, POS.VERB)
    ] == ["double"]
    assert lexicon.get_meanings("없는말", Language.KOREAN, POS.NOUN) == []
    assert lexicon.get_meanings("배", Language.ENGLISH, POS.NOUN) == []
    lexicon.close()


def test_manager_rejects_languages_without_a_lexicon(tmp_path):
    manager = LexiconManager(tmp_path)

    with pytest.raises(ValueError, match="not available for English documents"):
        manager.get_lexicon(Language.ENGLISH)
