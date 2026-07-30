from datetime import date
import sqlite3

import pytest

from app.domain.document import DocPart, Document
from app.domain.enums import Language, POS, Status
from app.domain.user import User
from app.domain.word import DocPartWord, Word
from app.repositories import Repository, SQLiteRepository, create_repository


@pytest.fixture
def repository(tmp_path):
    with SQLiteRepository(tmp_path / "luculent-test.db") as repo:
        yield repo


def test_sqlite_repository_implements_repository_contract():
    assert issubclass(SQLiteRepository, Repository)


def test_default_factory_creates_initialized_sqlite_repository(tmp_path):
    repository = create_repository(tmp_path / "factory-test.db")
    try:
        repository.save_user(User(1, "Vance"))
        assert repository.get_user(1).name == "Vance"
    finally:
        repository.close()


def test_user_round_trip_and_update(repository):
    repository.save_user(User(1, "Vance", date(2026, 7, 22)))

    user = repository.get_user(1)
    assert user.user_id == 1
    assert user.name == "Vance"
    assert user.created == date(2026, 7, 22)
    assert user.documents == []
    assert user.words == []

    repository.save_user(User(1, "Vance Baryn", date(2026, 7, 22)))
    assert repository.get_user(1).name == "Vance Baryn"
    assert repository.get_user(999) is None


def test_documents_and_parts_round_trip_in_reading_order(repository):
    repository.save_user(User(1, "Vance"))
    document = Document(
        document_id=10,
        title="어린 왕자",
        text="전체 원문",
        language=Language.KOREAN,
        imported=date(2026, 7, 22),
    )
    repository.save_document(1, document)
    repository.save_doc_part(
        10, DocPart(21, "두 번째 부분", position=1, readability=0.25)
    )
    repository.save_doc_part(
        10, DocPart(20, "첫 번째 부분", position=0, readability=0.75, active=True)
    )

    loaded = repository.get_document(10)
    assert loaded.title == "어린 왕자"
    assert loaded.text == "전체 원문"
    assert loaded.language is Language.KOREAN
    assert loaded.imported == date(2026, 7, 22)
    assert [part.doc_part_id for part in loaded.doc_parts] == [20, 21]
    assert loaded.doc_parts[0].active is True
    assert loaded.doc_parts[0].readability == pytest.approx(0.75)
    assert repository.get_document(999) is None


def test_user_loads_its_documents_and_words(repository):
    repository.save_user(User(1, "Vance"))
    repository.save_document(
        1, Document(10, "Title", "Text", Language.ENGLISH)
    )
    repository.save_word(1, Word(30, lemma="document"))

    loaded = repository.get_user(1)
    assert [document.document_id for document in loaded.documents] == [10]
    assert [word.word_id for word in loaded.words] == [30]


def test_word_round_trip_preserves_all_persistent_fields(repository):
    repository.save_user(User(1, "Vance"))
    word = Word(
        word_id=30,
        lemma="문서",
        english_definition="document",
        language=Language.KOREAN,
        pos=POS.NOUN,
    )
    word.korean_definition = "글이나 기록을 담은 것"
    word.gloss = "document"
    word.due = date(2026, 7, 25)
    word.difficulty = 4.5
    word.stability = 8.0
    word.image_path = "images/document.png"
    word.status = Status.LEARNING
    word.last_reviewed = date(2026, 7, 22)

    repository.save_word(1, word)
    loaded = repository.get_word(30)

    assert loaded.lemma == "문서"
    assert loaded.korean_definition == "글이나 기록을 담은 것"
    assert loaded.english_definition == "document"
    assert loaded.gloss == "document"
    assert loaded.due == date(2026, 7, 25)
    assert loaded.difficulty == pytest.approx(4.5)
    assert loaded.stability == pytest.approx(8.0)
    assert loaded.image_path == "images/document.png"
    assert loaded.status is Status.LEARNING
    assert loaded.last_reviewed == date(2026, 7, 22)
    assert loaded.pos is POS.NOUN
    assert loaded.language is Language.KOREAN
    assert repository.get_word(999) is None


def test_doc_part_word_round_trip(repository):
    repository.save_user(User(1, "Vance"))
    repository.save_document(
        1, Document(10, "Title", "Text", Language.KOREAN)
    )
    doc_part = DocPart(20, "문서가 있습니다.", position=0)
    word = Word(30, lemma="문서", english_definition="document")
    repository.save_doc_part(10, doc_part)
    repository.save_word(1, word)
    repository.save_doc_part_word(DocPartWord(word, doc_part, occurrences=4))

    associations = repository.list_doc_part_words(20)
    assert len(associations) == 1
    assert associations[0].word.word_id == 30
    assert associations[0].doc_part.doc_part_id == 20
    assert associations[0].occurrences == 4


def test_foreign_keys_prevent_orphaned_documents(repository):
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_document(
            999, Document(10, "Title", "Text", Language.ENGLISH)
        )
