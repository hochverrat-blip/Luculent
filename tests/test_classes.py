import pytest
from datetime import date
import pytest
from app.document import *
from app.enums import *
from app.word import *
from app.user import *


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
        definition="document",
        language=Language.KOREAN,
        pos=POS.NOUN,
    )


def test_language_values():
    assert Language.KOREAN.value == "Korean"
    assert Language.ENGLISH.value == "English"


def test_response_values():
    assert Response.KNOWN.value == "Known"
    assert Response.EASY.value == "Easy"
    assert Response.GOOD.value == "Good"
    assert Response.HARD.value == "Hard"


def test_status_values():
    assert Status.KNOWN.value == "Known"
    assert Status.LEARNING.value == "Learning"
    assert Status.NEW.value == "New"
    assert Status.SUSPENDED.value == "Suspended"


def test_pos_values():
    assert POS.VERB.value == "Verb"
    assert POS.NOUN.value == "Noun"
    assert POS.ADVERB.value == "Adverb"
    assert POS.ADJECTIVE.value == "Adjective"


def test_user_properties():
    user = the_user()
    assert user.user_id == 1
    assert user.name == "Vance"
    assert user.created == date(2026, 7, 22)
    assert user.documents == []
    assert user.words == []


def test_user_uses_today_as_default_creation_date():
    user = User(user_id=1, name="Vance")

    assert user.created == date.today()


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


def test_doc_part_default_values():
    doc_part = the_doc_part()
    assert doc_part.doc_part_id == 20
    assert doc_part.text == "이것은 첫 번째 부분입니다."
    assert doc_part.position == 0
    assert doc_part.readability == 0.0
    assert doc_part.active is False
    assert doc_part.doc_part_words == []


def test_doc_part_readability_can_be_changed():
    doc_part = the_doc_part()
    doc_part.readability = 0.85

    assert doc_part.readability == pytest.approx(0.85)


def test_doc_part_active_can_be_changed():
    doc_part = the_doc_part()
    doc_part.active = True

    assert doc_part.active is True


def test_word_properties():
    word = the_word()
    assert word.word_id == 30
    assert word.lemma == "문서"
    assert word.definition == "document"
    assert word.language is Language.KOREAN
    assert word.pos is POS.NOUN

    assert word.due is None
    assert word.difficulty == 0.0
    assert word.stability == 0.0
    assert word.image_path is None
    assert word.status is Status.NEW
    assert word.last_reviewed is None
    assert word.doc_part_words == []


def test_word_uses_expected_defaults():
    word = Word(word_id=30)

    assert word.lemma == ""
    assert word.definition == ""
    assert word.language is Language.KOREAN
    assert word.pos is POS.NOUN
    assert word.status is Status.NEW


def test_word_properties_can_be_updated():
    word = the_word()
    review_date = date(2026, 7, 22)
    due_date = date(2026, 7, 25)

    word.lemma = "문서들"
    word.definition = "documents"
    word.due = due_date
    word.difficulty = 4.5
    word.stability = 8.0
    word.image_path = "images/document.png"
    word.status = Status.LEARNING
    word.last_reviewed = review_date
    word.pos = POS.NOUN

    assert word.lemma == "문서들"
    assert word.definition == "documents"
    assert word.due == due_date
    assert word.difficulty == pytest.approx(4.5)
    assert word.stability == pytest.approx(8.0)
    assert word.image_path == "images/document.png"
    assert word.status is Status.LEARNING
    assert word.last_reviewed == review_date
    assert word.pos is POS.NOUN


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


def test_objects_can_be_added_to_lists():
    user = the_user()
    document = the_document()
    doc_part = the_doc_part()
    word = the_word()
    association = DocPartWord(
        word=word,
        doc_part=doc_part,
        occurrences=4,
    )

    user.documents.append(document)
    user.words.append(word)
    document.doc_parts.append(doc_part)
    doc_part.doc_part_words.append(association)
    word.doc_part_words.append(association)

    assert document in user.documents
    assert word in user.words
    assert doc_part in document.doc_parts
    assert association in doc_part.doc_part_words
    assert association in word.doc_part_words