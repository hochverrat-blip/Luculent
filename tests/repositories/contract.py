from datetime import date

import pytest

from app.domain.document import DocPart, Document
from app.domain.enums import Language, POS, Status
from app.domain.user import User
from app.domain.word import DocPartWord, Word
from app.repositories import Repository


class RepositoryContract:
    repository_class: type[Repository]

    def test_user_round_trip_and_update(self, repository):
        repository.save_user(User(101, "Vance", date(2026, 7, 22)))

        user = repository.get_user(101)
        assert user.user_id == 101
        assert user.name == "Vance"
        assert user.created == date(2026, 7, 22)
        assert user.native_language is Language.ENGLISH

        repository.save_user(User(101, "Vance Baryn", date(2026, 7, 22)))
        assert repository.get_user(101).name == "Vance Baryn"
        assert repository.get_user(2147483000) is None

    def test_user_lookup_by_name_and_deletion_by_id(self, repository):
        repository.save_user(User(102, "Lookup User"))

        loaded = repository.get_user_by_name("Lookup User")
        assert loaded.user_id == 102
        assert repository.get_user_by_name("Missing User") is None
        assert repository.delete_user(loaded.user_id) is True
        assert repository.delete_user(loaded.user_id) is False
        assert repository.get_user(102) is None

    def test_documents_and_parts_round_trip_in_reading_order(self, repository):
        repository.save_user(User(201, "Reader"))
        document = Document(
            202,
            "어린 왕자",
            "전체 원문",
            Language.KOREAN,
            date(2026, 7, 22),
        )
        repository.save_document(201, document)
        repository.save_doc_part(
            202, DocPart(204, "두 번째 부분", 1, readability=0.25)
        )
        repository.save_doc_part(
            202, DocPart(203, "첫 번째 부분", 0, readability=0.75, active=True)
        )

        loaded = repository.get_document(202)
        assert loaded.title == "어린 왕자"
        assert loaded.text == "전체 원문"
        assert loaded.language is Language.KOREAN
        assert loaded.imported == date(2026, 7, 22)
        assert [part.doc_part_id for part in loaded.doc_parts] == [203, 204]
        assert loaded.doc_parts[0].active is True
        assert loaded.doc_parts[0].readability == pytest.approx(0.75)
        assert repository.get_document(2147483000) is None

    def test_document_and_parts_are_saved_atomically(self, repository):
        repository.save_user(User(211, "Reader"))
        document = Document(None, "Title", "Text", Language.ENGLISH)
        document.doc_parts.extend(
            [
                DocPart(None, "First", 0),
                DocPart(None, "Duplicate position", 0),
            ]
        )

        with pytest.raises(Exception):
            repository.save_document_with_parts(211, document)

        assert document.document_id is None
        assert all(part.doc_part_id is None for part in document.doc_parts)
        assert repository.list_documents(211) == []

    def test_lists_a_users_documents_and_words_explicitly(self, repository):
        repository.save_user(User(301, "Vance"))
        repository.save_document(
            301, Document(302, "Title", "Text", Language.ENGLISH)
        )
        repository.save_word(301, Word(303, lemma="document"))

        documents = repository.list_documents(301)
        words = repository.list_words(301)

        assert [document.document_id for document in documents] == [302]
        assert [word.word_id for word in words] == [303]

    def test_word_round_trip_preserves_all_persistent_fields(self, repository):
        repository.save_user(User(401, "Vance"))
        word = Word(
            402,
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

        repository.save_word(401, word)
        loaded = repository.get_word(402)

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
        assert repository.get_word(2147483000) is None

    def test_doc_part_word_round_trip(self, repository):
        repository.save_user(User(501, "Vance"))
        repository.save_document(
            501, Document(502, "Title", "Text", Language.KOREAN)
        )
        doc_part = DocPart(503, "문서가 있습니다.", 0)
        word = Word(504, lemma="문서", english_definition="document")
        repository.save_doc_part(502, doc_part)
        repository.save_word(501, word)
        repository.save_doc_part_word(DocPartWord(word, doc_part, 4))

        associations = repository.list_doc_part_words(503)
        assert len(associations) == 1
        assert associations[0].word.word_id == 504
        assert associations[0].doc_part.doc_part_id == 503
        assert associations[0].occurrences == 4

    def test_lists_only_learning_words_in_users_active_parts(self, repository):
        repository.save_user(User(601, "Reader"))
        repository.save_user(User(602, "Other Reader"))
        repository.save_document(
            601, Document(603, "Reading", "Text", Language.ENGLISH)
        )
        active_part = DocPart(604, "Active", 0, active=True)
        inactive_part = DocPart(605, "Inactive", 1)
        repository.save_doc_part(603, active_part)
        repository.save_doc_part(603, inactive_part)

        included = Word(606, "included")
        included.status = Status.LEARNING
        inactive = Word(607, "inactive")
        inactive.status = Status.LEARNING
        not_learning = Word(608, "new")
        other_users = Word(609, "other")
        other_users.status = Status.LEARNING
        repository.save_word(601, included)
        repository.save_word(601, inactive)
        repository.save_word(601, not_learning)
        repository.save_word(602, other_users)
        repository.save_doc_part_word(DocPartWord(included, active_part, 1))
        repository.save_doc_part_word(DocPartWord(inactive, inactive_part, 1))
        repository.save_doc_part_word(DocPartWord(not_learning, active_part, 1))

        words = repository.list_learning_words_in_active_parts(601)

        assert [word.word_id for word in words] == [606]

    def test_rejects_doc_part_word_owned_by_different_users(self, repository):
        repository.save_user(User(611, "Document Owner"))
        repository.save_user(User(612, "Word Owner"))
        repository.save_document(
            611, Document(613, "Reading", "Text", Language.ENGLISH)
        )
        doc_part = DocPart(614, "Part", 0)
        word = Word(615, "word")
        repository.save_doc_part(613, doc_part)
        repository.save_word(612, word)

        with pytest.raises(ValueError, match="same user"):
            repository.save_doc_part_word(DocPartWord(word, doc_part, 1))

        assert repository.list_doc_part_words(614) == []

    def test_generated_primary_keys_are_unique(self, repository):
        first_user = User(None, "First")
        second_user = User(None, "Second")
        repository.save_user(first_user)
        repository.save_user(second_user)

        first_document = Document(None, "First", "Text", Language.ENGLISH)
        second_document = Document(None, "Second", "Text", Language.ENGLISH)
        repository.save_document(first_user.user_id, first_document)
        repository.save_document(first_user.user_id, second_document)

        first_part = DocPart(None, "First", 0)
        second_part = DocPart(None, "Second", 1)
        repository.save_doc_part(first_document.document_id, first_part)
        repository.save_doc_part(first_document.document_id, second_part)

        first_word = Word(None, "first")
        second_word = Word(None, "second")
        repository.save_word(first_user.user_id, first_word)
        repository.save_word(first_user.user_id, second_word)

        for first_id, second_id in (
            (first_user.user_id, second_user.user_id),
            (first_document.document_id, second_document.document_id),
            (first_part.doc_part_id, second_part.doc_part_id),
            (first_word.word_id, second_word.word_id),
        ):
            assert isinstance(first_id, int)
            assert isinstance(second_id, int)
            assert first_id != second_id

    def test_association_requires_saved_entities(self, repository):
        with pytest.raises(ValueError, match="must be saved first"):
            repository.save_doc_part_word(
                DocPartWord(Word(None), DocPart(None, "Text", 0), 1)
            )
