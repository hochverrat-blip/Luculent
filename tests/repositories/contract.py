from datetime import date, datetime, timezone

import pytest

from app.domain.document import DocPart, Document
from app.domain.enums import (
    Language,
    MeaningFrequency,
    MeaningLabel,
    POS,
    Response,
    Status,
)
from app.domain.user import User
from app.domain.word import (
    DocPartWord,
    UserWordMeaning,
    Word,
    WordMeaning,
    WordReview,
)
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

    def test_lists_users_by_name(self, repository):
        repository.save_user(User(103, "Zora"))
        repository.save_user(User(104, "Anna"))

        assert [user.user_id for user in repository.list_users()] == [104, 103]

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
        assert repository.get_users_doc_part(201, 203).doc_part_id == 203
        assert repository.get_users_doc_part(999, 203) is None
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

    def test_activating_part_deactivates_users_other_parts(self, repository):
        repository.save_user(User(215, "Reader"))
        repository.save_user(User(216, "Other Reader"))
        repository.save_document(
            215, Document(217, "First", "Text", Language.ENGLISH)
        )
        repository.save_document(
            215, Document(218, "Second", "Text", Language.ENGLISH)
        )
        repository.save_document(
            216, Document(219, "Other", "Text", Language.ENGLISH)
        )
        repository.save_doc_part(217, DocPart(220, "Old", 0, active=True))
        repository.save_doc_part(218, DocPart(221, "New", 0))
        repository.save_doc_part(219, DocPart(222, "Other", 0, active=True))

        repository.activate_doc_part(215, 221)

        assert repository.list_doc_parts(217)[0].active is False
        assert repository.list_doc_parts(218)[0].active is True
        assert repository.list_doc_parts(219)[0].active is True
        with pytest.raises(ValueError, match="belong"):
            repository.activate_doc_part(215, 222)

    def test_document_import_rolls_back_every_entity(self, repository):
        repository.save_user(User(221, "Document Owner"))
        repository.save_user(User(222, "Word Owner"))
        other_users_word = Word(223, "word")
        repository.save_word(222, other_users_word)
        document = Document(None, "Title", "Word.", Language.ENGLISH)
        doc_part = DocPart(None, "Word.", 0)
        new_word = Word(None, "new")
        new_meaning = WordMeaning(None, gloss="new meaning")
        new_word.meanings.append(new_meaning)
        document.doc_parts.append(doc_part)
        associations = [
            DocPartWord(new_word, doc_part, 1),
            DocPartWord(other_users_word, doc_part, 1),
        ]

        with pytest.raises(ValueError, match="same user"):
            repository.save_document_import(221, document, associations)

        assert document.document_id is None
        assert doc_part.doc_part_id is None
        assert new_word.word_id is None
        assert new_meaning.meaning_id is None
        assert repository.list_documents(221) == []
        assert repository.list_words(221) == []

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

    def test_deleting_document_removes_its_parts_but_keeps_user_words(
        self, repository
    ):
        repository.save_user(User(311, "Reader"))
        repository.save_user(User(312, "Other Reader"))
        document = Document(313, "Finished", "A word.", Language.ENGLISH)
        part = DocPart(314, "A word.", 0)
        word = Word(315, "word")
        repository.save_document(311, document)
        repository.save_doc_part(313, part)
        repository.save_word(311, word)
        repository.save_doc_part_word(DocPartWord(word, part, 1))

        assert repository.delete_document(312, 313) is False
        assert repository.delete_document(311, 313) is True
        assert repository.delete_document(311, 313) is False
        assert repository.get_document(313) is None
        assert repository.list_doc_parts(313) == []
        assert repository.list_doc_part_words(314) == []
        assert [stored.word_id for stored in repository.list_words(311)] == [315]

    def test_word_round_trip_preserves_all_persistent_fields(self, repository):
        repository.save_user(User(401, "Vance"))
        word = Word(
            402,
            lemma="문서",
            language=Language.KOREAN,
            pos=POS.NOUN,
        )
        word.due = datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc)
        word.difficulty = 4.5
        word.stability = 8.0
        word.image_path = "images/document.png"
        word.status = Status.LEARNING
        word.last_reviewed = datetime(2026, 7, 22, 14, 30, tzinfo=timezone.utc)
        word.step = 1

        repository.save_word(401, word)
        loaded = repository.get_word(402)

        assert loaded.lemma == "문서"
        assert loaded.due == datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc)
        assert loaded.difficulty == pytest.approx(4.5)
        assert loaded.stability == pytest.approx(8.0)
        assert loaded.image_path == "images/document.png"
        assert loaded.status is Status.LEARNING
        assert loaded.last_reviewed == datetime(
            2026, 7, 22, 14, 30, tzinfo=timezone.utc
        )
        assert loaded.step == 1
        assert loaded.pos is POS.NOUN
        assert loaded.language is Language.KOREAN
        assert repository.get_word(2147483000) is None
        assert [
            item.word_id
            for item in repository.list_words_by_lemmas(
                401, Language.KOREAN, {"문서", "없는단어"}
            )
        ] == [402]
        assert repository.list_words_by_lemmas(401, Language.ENGLISH, {"문서"}) == []
        assert repository.list_words_by_lemmas(401, Language.KOREAN, set()) == []

        verb = Word(403, lemma="문서", language=Language.KOREAN, pos=POS.VERB)
        repository.save_word(401, verb)
        matches = repository.list_words_by_lemmas(
            401, Language.KOREAN, {"문서"}
        )
        assert {(item.word_id, item.pos) for item in matches} == {
            (402, POS.NOUN),
            (403, POS.VERB),
        }

    def test_word_meanings_round_trip_in_display_order(self, repository):
        repository.save_user(User(411, "Vance"))
        word = Word(412, lemma="배", language=Language.KOREAN, pos=POS.NOUN)
        repository.save_word(411, word)
        rare = WordMeaning(
            414,
            korean_definition="물을 건너는 운송 수단",
            english_definition="a vessel used on water",
            gloss="boat",
            frequency=MeaningFrequency.RARE,
            labels={MeaningLabel.ARCHAIC, MeaningLabel.TECHNICAL},
            display_order=2,
        )
        common = WordMeaning(
            413,
            korean_definition="사람의 몸통 가운데 부분",
            english_definition="the abdomen",
            gloss="stomach",
            display_order=1,
        )

        repository.save_word_meaning(412, rare)
        repository.save_word_meaning(412, common)

        loaded = repository.get_word(412)
        assert [meaning.meaning_id for meaning in loaded.meanings] == [413, 414]
        assert loaded.meanings[0].frequency is MeaningFrequency.COMMON
        assert loaded.meanings[0].labels == set()
        assert loaded.meanings[1].korean_definition == "물을 건너는 운송 수단"
        assert loaded.meanings[1].english_definition == "a vessel used on water"
        assert loaded.meanings[1].gloss == "boat"
        assert loaded.meanings[1].frequency is MeaningFrequency.RARE
        assert loaded.meanings[1].labels == {
            MeaningLabel.ARCHAIC,
            MeaningLabel.TECHNICAL,
        }

        rare.gloss = "ship"
        rare.labels.remove(MeaningLabel.ARCHAIC)
        repository.save_word_meaning(412, rare)

        updated = repository.list_word_meanings(412)[1]
        assert updated.gloss == "ship"
        assert updated.labels == {MeaningLabel.TECHNICAL}

    def test_lexicon_meanings_are_shared_between_users(self, repository):
        meaning = WordMeaning(
            None,
            korean_definition="물 위로 다니는 운송 수단",
            english_definition="a vessel used on water",
            gloss="boat",
        )
        repository.install_lexicon(
            "test lexicon",
            "1",
            "checksum",
            [("배", Language.KOREAN, POS.NOUN, meaning)],
        )
        repository.save_user(User(421, "First reader"))
        repository.save_user(User(422, "Second reader"))
        first_word = Word(423, "배", Language.KOREAN, POS.NOUN)
        second_word = Word(424, "배", Language.KOREAN, POS.NOUN)
        repository.save_word(421, first_word)
        repository.save_word(422, second_word)

        first_meaning = repository.get_word(423).meanings[0]
        second_meaning = repository.get_word(424).meanings[0]

        assert repository.get_lexicon_version("test lexicon") == "1"
        assert first_meaning.meaning_id == second_meaning.meaning_id
        assert first_meaning.gloss == second_meaning.gloss == "boat"

    def test_user_meanings_are_owned_by_one_users_word(self, repository):
        repository.save_user(User(431, "Reader"))
        repository.save_user(User(432, "Other Reader"))
        word = Word(433, "배", Language.KOREAN, POS.NOUN)
        repository.save_word(431, word)
        repository.save_word_meaning(433, WordMeaning(None, gloss="boat"))
        meaning = UserWordMeaning(
            None,
            433,
            korean_definition="내가 외울 뜻",
            english_definition="my definition",
            gloss="mine",
        )

        repository.save_user_word_meaning(431, meaning)
        loaded = repository.get_word(433)

        assert isinstance(meaning.user_meaning_id, int)
        assert [item.gloss for item in loaded.meanings] == ["boat"]
        assert [item.gloss for item in loaded.user_meanings] == ["mine"]
        assert repository.delete_user_word_meaning(
            432, meaning.user_meaning_id
        ) is False
        assert repository.delete_user_word_meaning(
            431, meaning.user_meaning_id
        ) is True
        assert repository.get_word(433).meanings[0].gloss == "boat"
        assert repository.get_word(433).user_meanings == []

    def test_doc_part_word_round_trip(self, repository):
        repository.save_user(User(501, "Vance"))
        repository.save_document(
            501, Document(502, "Title", "Text", Language.KOREAN)
        )
        doc_part = DocPart(503, "문서가 있습니다.", 0)
        word = Word(504, lemma="문서")
        repository.save_doc_part(502, doc_part)
        repository.save_word(501, word)
        repository.save_doc_part_word(DocPartWord(word, doc_part, 4))

        associations = repository.list_doc_part_words(503)
        users_associations = repository.list_users_doc_part_words(501)
        assert len(associations) == 1
        assert associations[0].word.word_id == 504
        assert associations[0].doc_part.doc_part_id == 503
        assert associations[0].occurrences == 4
        assert len(users_associations) == 1
        assert users_associations[0].word.word_id == 504
        assert users_associations[0].doc_part.doc_part_id == 503

    def test_gets_due_words_in_users_active_parts_one_at_a_time(self, repository):
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
        included.due = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        inactive = Word(607, "inactive")
        inactive.status = Status.LEARNING
        new_word = Word(608, "new")
        other_users = Word(609, "other")
        other_users.status = Status.LEARNING
        future = Word(610, "future")
        future.status = Status.LEARNING
        future.due = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        repository.save_word(601, included)
        repository.save_word(601, inactive)
        repository.save_word(601, new_word)
        repository.save_word(602, other_users)
        repository.save_word(601, future)
        repository.save_doc_part_word(DocPartWord(included, active_part, 1))
        repository.save_doc_part_word(DocPartWord(inactive, inactive_part, 1))
        repository.save_doc_part_word(DocPartWord(new_word, active_part, 1))
        repository.save_doc_part_word(DocPartWord(future, active_part, 1))

        assert repository.get_user_word(601, included.word_id).word_id == 606
        assert repository.get_user_word(602, included.word_id) is None
        assert repository.count_due_words_in_active_parts(
            601, datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        ) == 2

        first = repository.get_due_word_in_active_parts(
            601, datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        )
        first.status = Status.KNOWN
        repository.update_word_study(first)
        second = repository.get_due_word_in_active_parts(
            601,
            datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc),
            first.word_id,
        )
        second.status = Status.KNOWN
        repository.update_word_study(second)

        assert {first.word_id, second.word_id} == {606, 608}
        assert repository.get_due_word_in_active_parts(
            601, datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        ) is None
        assert repository.count_due_words_in_active_parts(
            601, datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        ) == 0

    def test_updates_only_word_study_fields(self, repository):
        repository.save_user(User(621, "Reader"))
        word = Word(622, "word")
        repository.save_word(621, word)
        word.status = Status.LEARNING
        word.difficulty = 4.9
        word.stability = 3.0
        word.last_reviewed = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        word.due = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        word.step = 1

        repository.update_word_study(word)

        loaded = repository.get_word(622)
        assert loaded.status is Status.LEARNING
        assert loaded.difficulty == pytest.approx(4.9)
        assert loaded.stability == pytest.approx(3.0)
        assert loaded.last_reviewed == datetime(
            2026, 7, 22, 12, 0, tzinfo=timezone.utc
        )
        assert loaded.due == datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        assert loaded.step == 1

    def test_word_reviews_round_trip(self, repository):
        repository.save_user(User(631, "Reader"))
        word = Word(632, "word")
        repository.save_word(631, word)
        reviewed_at = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        word.status = Status.LEARNING
        word.step = 0
        word.due = reviewed_at
        review = WordReview(
            None,
            632,
            Response.AGAIN,
            Status.REVIEW,
            reviewed_at,
            2400,
        )

        repository.record_word_review(word, review)

        reviews = repository.list_word_reviews(632)
        assert isinstance(review.review_id, int)
        assert len(reviews) == 1
        assert reviews[0].review_id == review.review_id
        assert reviews[0].response is Response.AGAIN
        assert reviews[0].status_before is Status.REVIEW
        assert reviews[0].reviewed_at == reviewed_at
        assert reviews[0].duration_ms == 2400
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

        first_meaning = WordMeaning(None, gloss="first")
        second_meaning = WordMeaning(None, gloss="second")
        repository.save_word_meaning(first_word.word_id, first_meaning)
        repository.save_word_meaning(first_word.word_id, second_meaning)

        for first_id, second_id in (
            (first_user.user_id, second_user.user_id),
            (first_document.document_id, second_document.document_id),
            (first_part.doc_part_id, second_part.doc_part_id),
            (first_word.word_id, second_word.word_id),
            (first_meaning.meaning_id, second_meaning.meaning_id),
        ):
            assert isinstance(first_id, int)
            assert isinstance(second_id, int)
            assert first_id != second_id

    def test_association_requires_saved_entities(self, repository):
        with pytest.raises(ValueError, match="must be saved first"):
            repository.save_doc_part_word(
                DocPartWord(Word(None), DocPart(None, "Text", 0), 1)
            )
