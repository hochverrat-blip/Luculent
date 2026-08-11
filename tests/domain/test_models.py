from datetime import date, datetime, timezone

import pytest
from app.domain.document import *
from app.domain.enums import *
from app.domain.word import *
from app.domain.user import *


def the_user():
    return User(
        user_id=1,
        name="Vance",
        created=date(2026, 7, 22),
    )


def the_document():
    return Document(
        document_id=10,
        title="어린 왕자",
        text="이것은 시험 문서입니다.",
        language=Language.KOREAN,
        imported=date(2026, 7, 22),
    )


def the_doc_part():
    return DocPart(
        doc_part_id=20,
        text="이것은 첫 번째 부분입니다.",
        position=0,
    )


def the_word():
    return Word(
        word_id=30,
        lemma="문서",
        language=Language.KOREAN,
        pos=POS.NOUN,
    )


def test_enum_values():
    assert {item.name: item.value for item in Language} == {
        "KOREAN": "Korean",
        "ENGLISH": "English",
    }
    assert {item.name: item.value for item in Response} == {
        "AGAIN": "Again",
        "EASY": "Easy",
        "GOOD": "Good",
        "HARD": "Hard",
    }
    assert {item.name: item.value for item in Status} == {
        "KNOWN": "Known",
        "LEARNING": "Learning",
        "NEW": "New",
        "RELEARNING": "Relearning",
        "REVIEW": "Review",
        "SUSPENDED": "Suspended",
    }
    assert {item.name: item.value for item in POS} == {
        "VERB": "Verb",
        "NOUN": "Noun",
        "ADVERB": "Adverb",
        "ADJECTIVE": "Adjective",
    }
    assert {item.name: item.value for item in MeaningFrequency} == {
        "COMMON": "Common",
        "RARE": "Rare",
    }
    assert {item.name: item.value for item in MeaningLabel} == {
        "ARCHAIC": "Archaic",
        "TECHNICAL": "Technical",
    }


def test_user_properties():
    user = the_user()
    assert user.user_id == 1
    assert user.name == "Vance"
    assert user.created == date(2026, 7, 22)
    assert user.native_language is Language.ENGLISH


def test_user_uses_today_as_default_creation_date():
    user = User(user_id=1, name="Vance")

    assert user.created == date.today()


def test_user_rejects_an_unsupported_native_language():
    with pytest.raises(ValueError, match="Only English"):
        User(user_id=1, name="Vance", native_language=Language.KOREAN)


def test_document_properties():
    document = the_document()
    assert document.document_id == 10
    assert document.title == "어린 왕자"
    assert document.text == "이것은 시험 문서입니다."
    assert document.language is Language.KOREAN
    assert document.imported == date(2026, 7, 22)
    assert document.doc_parts == []


def test_document_uses_today_as_default_import_date():
    document = Document(
        document_id=10,
        title="Test",
        text="Test text",
        language=Language.ENGLISH,
    )

    assert document.imported == date.today()


def test_doc_part_properties_defaults_and_updates():
    doc_part = the_doc_part()
    assert doc_part.doc_part_id == 20
    assert doc_part.text == "이것은 첫 번째 부분입니다."
    assert doc_part.position == 0
    assert doc_part.readability == 0.0
    assert doc_part.active is False
    assert doc_part.doc_part_words == []

    doc_part.readability = 0.85
    doc_part.active = True

    assert doc_part.readability == pytest.approx(0.85)
    assert doc_part.active is True


def test_word_properties():
    word = the_word()
    assert word.word_id == 30
    assert word.lemma == "문서"
    assert word.language is Language.KOREAN
    assert word.pos is POS.NOUN
    assert word.meanings == []
    assert word.user_meanings == []

    assert word.due is None
    assert word.difficulty == 0.0
    assert word.stability == 0.0
    assert word.image_path is None
    assert word.status is Status.NEW
    assert word.last_reviewed is None
    assert word.step is None
    assert word.doc_part_words == []
    assert Word(word_id=31).lemma == ""


def test_word_properties_can_be_updated():
    word = the_word()
    review_date = datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc)
    due_date = datetime(2026, 7, 25, 12, 30, tzinfo=timezone.utc)

    word.lemma = "문서들"
    word.due = due_date
    word.difficulty = 4.5
    word.stability = 8.0
    word.image_path = "images/document.png"
    word.status = Status.LEARNING
    word.last_reviewed = review_date
    word.step = 1
    word.pos = POS.NOUN

    assert word.lemma == "문서들"
    assert word.due == due_date
    assert word.difficulty == pytest.approx(4.5)
    assert word.stability == pytest.approx(8.0)
    assert word.image_path == "images/document.png"
    assert word.status is Status.LEARNING
    assert word.last_reviewed == review_date
    assert word.step == 1
    assert word.pos is POS.NOUN


def test_word_meaning_properties_and_updates():
    meaning = WordMeaning(
        meaning_id=40,
        korean_definition="기록을 담은 것",
        english_definition="a written record",
        gloss="document",
        frequency=MeaningFrequency.RARE,
        labels={MeaningLabel.TECHNICAL},
        display_order=2,
    )

    assert meaning.meaning_id == 40
    assert meaning.korean_definition == "기록을 담은 것"
    assert meaning.english_definition == "a written record"
    assert meaning.gloss == "document"
    assert meaning.frequency is MeaningFrequency.RARE
    assert meaning.labels == {MeaningLabel.TECHNICAL}
    assert meaning.display_order == 2

    meaning.korean_definition = "기록"
    meaning.english_definition = "record"
    meaning.gloss = "record"
    meaning.frequency = MeaningFrequency.COMMON
    meaning.labels.add(MeaningLabel.ARCHAIC)
    meaning.display_order = 1

    assert meaning.korean_definition == "기록"
    assert meaning.english_definition == "record"
    assert meaning.gloss == "record"
    assert meaning.frequency is MeaningFrequency.COMMON
    assert meaning.labels == {MeaningLabel.TECHNICAL, MeaningLabel.ARCHAIC}
    assert meaning.display_order == 1


def test_user_word_meaning_properties_and_updates():
    meaning = UserWordMeaning(
        50,
        40,
        korean_definition="사용자 정의",
        english_definition="user definition",
        gloss="personal",
        display_order=2,
    )

    meaning.korean_definition = "수정"
    meaning.english_definition = "edited"
    meaning.gloss = "mine"
    meaning.display_order = 1

    assert meaning.user_meaning_id == 50
    assert meaning.word_id == 40
    assert meaning.korean_definition == "수정"
    assert meaning.english_definition == "edited"
    assert meaning.gloss == "mine"
    assert meaning.display_order == 1


def test_doc_part_word_properties():
    word = the_word()
    doc_part = the_doc_part()
    association = DocPartWord(
        word=word,
        doc_part=doc_part,
        occurrences=4,
    )

    assert association.word is word
    assert association.doc_part is doc_part
    assert association.occurrences == 4
