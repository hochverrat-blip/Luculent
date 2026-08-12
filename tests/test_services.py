from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.settings as settings_module
import app.services.document_service as document_service_module
from app.domain import (
    DocPart,
    DocPartWord,
    Document,
    Language,
    POS,
    Response,
    Status,
    User,
    Word,
    WordMeaning,
)
from app.lexicon import LexiconManager
from app.scraper import ScrapedPage, Scraper
from app.services import DocumentService, UserService, WordService


@pytest.fixture(autouse=True)
def use_fake_lexicon(monkeypatch):
    def install(repository, language):
        source = f"test-{language.name}"
        if repository.get_lexicon_version(source) is not None:
            return
        meanings = []
        if language is Language.ENGLISH:
            meanings.append(
                (
                    "cat",
                    language,
                    POS.NOUN,
                    WordMeaning(
                        None,
                        english_definition="The meaning of cat",
                        gloss="meaning of cat",
                    ),
                )
            )
        repository.install_lexicon(source, "1", "test", meanings)

    monkeypatch.setattr(
        document_service_module,
        "ensure_lexicon",
        install,
    )


@pytest.fixture
def configured_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.txt"
    path.write_text(
        f"database=sqlite\nsqlite_path={tmp_path / 'services.db'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", path)
    return path


@pytest.fixture
def service_context(configured_settings, monkeypatch):
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    with UserService() as user_service:
        with DocumentService() as document_service:
            yield user_service, document_service


def test_new_get_and_delete_user(service_context):
    user_service, _ = service_context
    user = user_service.new_user(" Vance ")

    assert isinstance(user, User)
    assert isinstance(user.user_id, int)
    assert user.name == "Vance"
    assert user_service.get_user("Vance").user_id == user.user_id
    assert user_service.delete_user(user) is True
    assert user_service.delete_user(user) is False
    assert user_service.get_user("Vance") is None


def test_delete_user_requires_a_saved_user(service_context):
    user_service, _ = service_context

    with pytest.raises(ValueError, match="saved"):
        user_service.delete_user(User(None, "Vance"))


def test_new_user_rejects_blank_and_duplicate_names(service_context):
    user_service, _ = service_context
    with pytest.raises(ValueError, match="required"):
        user_service.new_user("   ")

    user_service.new_user("Vance")
    with pytest.raises(ValueError, match="already exists"):
        user_service.new_user("vAnCe")
    assert user_service.get_user("VANCE").name == "Vance"


def test_import_document_file_preserves_source_and_builds_ordered_parts(
    service_context, tmp_path
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    sentence_lengths = [290, 20, 290]
    source = " ".join(
        " ".join(f"sentence-{sentence}-{word}" for word in range(length)) + "."
        for sentence, length in enumerate(sentence_lengths)
    )
    path = tmp_path / "reading.txt"
    path.write_text(source, encoding="utf-8")

    document = document_service.import_document_file(user, path)

    assert isinstance(document.document_id, int)
    assert document.title == "reading"
    assert document.text == source
    assert document.language is Language.ENGLISH
    assert all(isinstance(part.doc_part_id, int) for part in document.doc_parts)
    assert [part.position for part in document.doc_parts] == [0, 1, 2]
    assert [len(part.text.split()) for part in document.doc_parts] == sentence_lengths
    loaded = document_service._repository.get_document(document.document_id)
    assert loaded.document_id == document.document_id
    assert [len(part.text.split()) for part in loaded.doc_parts] == sentence_lengths


def test_import_keeps_a_sentence_longer_than_part_limit_intact(
    service_context, tmp_path
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    source = " ".join(f"word-{index}" for index in range(301)) + "."
    path = tmp_path / "long-sentence.txt"
    path.write_text(source, encoding="utf-8")

    document = document_service.import_document_file(user, path)

    assert len(document.doc_parts) == 1
    assert document.doc_parts[0].text == source
    assert len(document.doc_parts[0].text.split()) == 301


def test_import_document_url_extracts_visible_text_and_title(
    configured_settings, monkeypatch
):
    monkeypatch.setattr(
        Scraper,
        "scrape",
        classmethod(
            lambda cls, url: ScrapedPage(
                "Reading title", "First paragraph. Second."
            )
        ),
    )
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    with UserService() as user_service:
        with DocumentService() as document_service:
            user = user_service.new_user("Reader")

            document = document_service.import_document_url(
                user, "https://example.com/article"
            )

            loaded = document_service._repository.get_document(
                document.document_id
            )
    assert document.title == "Reading title"
    assert document.text == "First paragraph. Second."
    assert document.doc_parts[0].text == "First paragraph. Second."
    assert loaded.text == "First paragraph. Second."


def test_get_documents_returns_only_the_users_documents(
    configured_settings, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    path = tmp_path / "reading.txt"
    path.write_text("A short document.", encoding="utf-8")
    with UserService() as user_service:
        with DocumentService() as document_service:
            reader = user_service.new_user("Reader")
            other_reader = user_service.new_user("Other Reader")
            imported = document_service.import_document_file(reader, path)

            documents = document_service.get_documents(reader)

            assert [document.document_id for document in documents] == [
                imported.document_id
            ]
            assert document_service.get_documents(other_reader) == []
            assert (
                document_service.get_docpart(
                    reader, imported.doc_parts[0].doc_part_id
                ).doc_part_id
                == imported.doc_parts[0].doc_part_id
            )
            assert (
                document_service.get_docpart(
                    other_reader, imported.doc_parts[0].doc_part_id
                )
                is None
            )
            with pytest.raises(ValueError, match="saved"):
                document_service.get_documents(User(None, "Unsaved"))


def test_document_readability_uses_projected_recall_and_untracked_words(
    service_context, monkeypatch
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    document = Document(None, "Reading", "Known learning plus filler.", Language.ENGLISH)
    part = DocPart(None, document.text, 0)
    known = Word(None, "known", Language.ENGLISH)
    known.status = Status.KNOWN
    learning = Word(None, "learning", Language.ENGLISH)
    document_service._repository.save_document(user.user_id, document)
    document_service._repository.save_doc_part(document.document_id, part)
    document_service._repository.save_word(user.user_id, known)
    document_service._repository.save_word(user.user_id, learning)
    document_service._repository.save_doc_part_word(DocPartWord(known, part, 1))
    document_service._repository.save_doc_part_word(DocPartWord(learning, part, 1))
    monkeypatch.setattr(
        WordService,
        "get_projected_retrievability",
        staticmethod(lambda word: 1.0 if word.status is Status.KNOWN else 0.5),
    )
    loaded = document_service.get_documents(user)

    assert loaded[0].doc_parts[0].readability == pytest.approx(0.875)


def test_projected_retrievability_reflects_memory_strength():
    reviewed_at = datetime.now(timezone.utc)
    weak = Word(1, "weak")
    weak.status = Status.LEARNING
    weak.stability = 0.212
    weak.last_reviewed = reviewed_at
    strong = Word(2, "strong")
    strong.status = Status.REVIEW
    strong.stability = 8.2956
    strong.last_reviewed = reviewed_at
    known = Word(3, "known")
    known.status = Status.KNOWN

    weak_score = WordService.get_projected_retrievability(weak)
    strong_score = WordService.get_projected_retrievability(strong)

    assert 0.0 < weak_score < strong_score < 1.0
    assert WordService.get_projected_retrievability(known) == 1.0


def test_delete_document_requires_ownership_and_a_saved_document(service_context):
    user_service, document_service = service_context
    reader = user_service.new_user("Reader")
    other_reader = user_service.new_user("Other Reader")
    document = Document(None, "Finished", "Text", Language.ENGLISH)
    document_service._repository.save_document(reader.user_id, document)

    assert document_service.delete_document(other_reader, document) is False
    assert document_service.delete_document(reader, document) is True
    assert document_service.get_documents(reader) == []
    with pytest.raises(ValueError, match="saved"):
        document_service.delete_document(
            reader, Document(None, "Unsaved", "Text", Language.ENGLISH)
        )


def test_import_stores_unique_content_lemmas_and_part_occurrences(
    service_context, tmp_path
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    path = tmp_path / "words.txt"
    path.write_text(
        "Cats chase mice quickly. The cats sleep.",
        encoding="utf-8",
    )

    first_document = document_service.import_document_file(user, path)
    second_document = document_service.import_document_file(user, path)
    words = document_service._repository.list_words(user.user_id)
    words_by_lemma = {word.lemma: word for word in words}

    assert set(words_by_lemma) == {"cat", "chase", "mouse", "quickly", "sleep"}
    assert words_by_lemma["cat"].pos is POS.NOUN
    assert words_by_lemma["chase"].pos is POS.VERB
    assert words_by_lemma["quickly"].pos is POS.ADVERB
    assert words_by_lemma["cat"].meanings[0].gloss == "meaning of cat"
    assert len(words_by_lemma["cat"].meanings) == 1
    assert isinstance(words_by_lemma["cat"].meanings[0].meaning_id, int)
    for document in (first_document, second_document):
        associations = document_service._repository.list_doc_part_words(
            document.doc_parts[0].doc_part_id
        )
        occurrences = {
            association.word.lemma: association.occurrences
            for association in associations
        }
        assert occurrences == {
            "cat": 2,
            "chase": 1,
            "mouse": 1,
            "quickly": 1,
            "sleep": 1,
        }


def test_activate_docpart_makes_it_users_only_active_part(
    service_context, tmp_path
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    path = tmp_path / "reading.txt"
    path.write_text("First sentence. Second sentence.", encoding="utf-8")
    first = document_service.import_document_file(user, path)
    second = document_service.import_document_file(user, path)

    document_service.activate_docpart(user, first.doc_parts[0])
    document_service.activate_docpart(user, second.doc_parts[0])

    loaded = document_service.get_documents(user)
    active_ids = {
        part.doc_part_id
        for document in loaded
        for part in document.doc_parts
        if part.active
    }
    assert active_ids == {second.doc_parts[0].doc_part_id}
    assert second.doc_parts[0].active is True


def test_get_md_text_bolds_studied_words_but_not_known_words(
    service_context, tmp_path, monkeypatch
):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    path = tmp_path / "reading.txt"
    path.write_text("Cats chase mice quickly.", encoding="utf-8")
    document = document_service.import_document_file(user, path)
    part = document.doc_parts[0]
    words = document_service._repository.list_words(user.user_id)
    cat = next(word for word in words if word.lemma == "cat")
    cat.status = Status.KNOWN
    document_service._repository.update_word_study(cat)
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: pytest.fail("stored language should be used")),
    )

    marked = document_service.get_md_text(user, part)

    assert marked == "Cats **chase** **mice** **quickly**."


def test_import_normalizes_korean_lemmas(service_context, tmp_path, monkeypatch):
    user_service, document_service = service_context
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "ko"),
    )
    user = user_service.new_user("Reader")
    path = tmp_path / "korean.txt"
    path.write_text(
        "어제 서울에서 학생들이 배고픈 고양이한태 생선을 주었지만, "
        "고양이는 먹지 않았다. 고양이가 빠르게 달려와 생선을 맛있게 "
        "먹었고, 학생들은 그 모습을 보며 행복해했다.",
        encoding="utf-8",
    )

    document = document_service.import_document_file(user, path)

    words = document_service._repository.list_words(user.user_id)
    words_by_lemma = {word.lemma: word for word in words}
    assert set(words_by_lemma) == {
        "어제",
        "서울",
        "학생",
        "배고프다",
        "고양이",
        "생선",
        "주다",
        "먹다",
        "빠르다",
        "달려오다",
        "맛있다",
        "모습",
        "보다",
        "행복하다",
    }
    assert words_by_lemma["고양이"].pos is POS.NOUN
    assert words_by_lemma["먹다"].pos is POS.VERB
    assert words_by_lemma["배고프다"].pos is POS.ADJECTIVE
    assert words_by_lemma["어제"].pos is POS.ADVERB
    assert words_by_lemma["서울"].pos is POS.NOUN
    assert words_by_lemma["행복하다"].pos is POS.ADJECTIVE
    associations = document_service._repository.list_doc_part_words(
        document.doc_parts[0].doc_part_id
    )
    assert {
        association.word.lemma: association.occurrences
        for association in associations
    } == {
        "어제": 1,
        "서울": 1,
        "학생": 2,
        "배고프다": 1,
        "고양이": 3,
        "생선": 2,
        "주다": 1,
        "먹다": 2,
        "빠르다": 1,
        "달려오다": 1,
        "맛있다": 1,
        "모습": 1,
        "보다": 1,
        "행복하다": 1,
    }


@pytest.mark.parametrize("source", ["", "   \n\t"])
def test_import_rejects_empty_documents(service_context, tmp_path, source):
    user_service, document_service = service_context
    user = user_service.new_user("Reader")
    path = tmp_path / "empty.txt"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="empty document"):
        document_service.import_document_file(user, path)


def test_import_requires_a_saved_user(service_context, tmp_path):
    _, document_service = service_context
    path = tmp_path / "reading.txt"
    path.write_text("Some text", encoding="utf-8")

    with pytest.raises(ValueError, match="saved"):
        document_service.import_document_file(User(None, "Reader"), path)


def test_import_detects_korean(configured_settings, tmp_path):
    path = tmp_path / "korean.txt"
    path.write_text(
        "한국어로 작성한 문서입니다. 독자는 이 문서를 읽고 새로운 단어를 공부합니다. "
        "문서의 언어를 자동으로 확인하고 저장합니다.",
        encoding="utf-8",
    )
    with UserService() as user_service:
        with DocumentService() as document_service:
            user = user_service.new_user("Reader")

            document = document_service.import_document_file(user, path)

    assert document.language is Language.KOREAN


def test_import_rejects_unsupported_detected_language(
    configured_settings, tmp_path, monkeypatch
):
    path = tmp_path / "unsupported.txt"
    path.write_text("Un texte en français.", encoding="utf-8")
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "fr"),
    )
    with UserService() as user_service:
        with DocumentService() as document_service:
            user = user_service.new_user("Reader")

            with pytest.raises(ValueError, match="Unsupported document language: fr"):
                document_service.import_document_file(user, path)


def test_import_rejects_english_without_saving_partial_data(
    configured_settings, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    monkeypatch.setattr(
        document_service_module,
        "ensure_lexicon",
        LexiconManager().ensure_installed,
    )
    path = tmp_path / "english.txt"
    path.write_text("Cats sleep.", encoding="utf-8")
    with UserService() as user_service:
        with DocumentService() as document_service:
            user = user_service.new_user("Reader")

            with pytest.raises(
                ValueError, match="not available for English documents"
            ):
                document_service.import_document_file(user, path)

            assert document_service.get_documents(user) == []
            assert document_service._repository.list_words(user.user_id) == []


def test_get_due_returns_only_due_words_in_active_parts(
    configured_settings, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    path = tmp_path / "reading.txt"
    path.write_text("The.", encoding="utf-8")

    with UserService() as user_service:
        with DocumentService() as document_service:
            with WordService() as word_service:
                user = user_service.new_user("Reader")
                document = document_service.import_document_file(user, path)
                active_part = document.doc_parts[0]
                active_part.active = True
                word_service._repository.save_doc_part(
                    document.document_id, active_part
                )
                inactive_part = DocPart(None, "Inactive", 1)
                word_service._repository.save_doc_part(
                    document.document_id, inactive_part
                )

                new_word = Word(None, "new")
                due = Word(None, "due")
                due.status = Status.REVIEW
                due.due = datetime.now(timezone.utc)
                second_due = Word(None, "second due")
                second_due.status = Status.REVIEW
                second_due.due = datetime.now(timezone.utc)
                future = Word(None, "future")
                future.status = Status.LEARNING
                future.due = datetime.now(timezone.utc) + timedelta(days=1)
                known = Word(None, "known")
                known.status = Status.KNOWN
                inactive = Word(None, "inactive")
                inactive.status = Status.LEARNING
                reviewed_today = Word(None, "reviewed today")
                reviewed_today.status = Status.REVIEW
                reviewed_today.stability = 3.0
                reviewed_today.difficulty = 5.0
                reviewed_today.last_reviewed = datetime.now(
                    timezone.utc
                ) - timedelta(days=3)
                reviewed_today.due = datetime.now(timezone.utc)
                for word in (
                    new_word,
                    due,
                    second_due,
                    future,
                    known,
                    inactive,
                    reviewed_today,
                ):
                    word_service._repository.save_word(user.user_id, word)
                word_service._repository.save_word_meaning(
                    new_word.word_id, WordMeaning(None, gloss="new meaning")
                )
                for word in (new_word, due, second_due, future, known):
                    word_service._repository.save_doc_part_word(
                        DocPartWord(word, active_part, 1)
                    )
                word_service._repository.save_doc_part_word(
                    DocPartWord(inactive, inactive_part, 1)
                )
                word_service.record_response(user, reviewed_today, Response.GOOD)

                words = []
                for _ in range(3):
                    word = word_service.get_due(user)
                    words.append(word)
                    word_service.mark_known(user, word)
                no_more_due = word_service.get_due(user)

    assert {word.word_id for word in words} == {
        new_word.word_id,
        due.word_id,
        second_due.word_id,
    }
    assert no_more_due is None
    loaded_new = next(word for word in words if word.word_id == new_word.word_id)
    assert loaded_new.meanings[0].gloss == "new meaning"


def test_get_due_requires_a_saved_user(configured_settings):
    with WordService() as word_service:
        with pytest.raises(ValueError, match="saved"):
            word_service.get_due(User(None, "Reader"))


def test_get_due_looks_ahead_twenty_minutes_when_nothing_is_due(
    configured_settings,
):
    with UserService() as user_service:
        with DocumentService() as document_service:
            with WordService() as word_service:
                user = user_service.new_user("Reader")
                document = Document(None, "Reading", "Text", Language.KOREAN)
                document_service._repository.save_document(user.user_id, document)
                part = DocPart(None, "Text", 0, active=True)
                document_service._repository.save_doc_part(
                    document.document_id, part
                )

                soon = Word(None, "곧")
                soon.status = Status.LEARNING
                soon.due = datetime.now(timezone.utc) + timedelta(minutes=19)
                later = Word(None, "나중")
                later.status = Status.LEARNING
                later.due = datetime.now(timezone.utc) + timedelta(minutes=21)
                for word in (soon, later):
                    word_service._repository.save_word(user.user_id, word)
                    word_service._repository.save_doc_part_word(
                        DocPartWord(word, part, 1)
                    )

                result = word_service.get_due(user)

    assert result.word_id == soon.word_id


def test_get_due_does_not_look_ahead_while_a_word_is_due(configured_settings):
    with UserService() as user_service:
        with DocumentService() as document_service:
            with WordService() as word_service:
                user = user_service.new_user("Reader")
                document = Document(None, "Reading", "Text", Language.KOREAN)
                document_service._repository.save_document(user.user_id, document)
                part = DocPart(None, "Text", 0, active=True)
                document_service._repository.save_doc_part(
                    document.document_id, part
                )

                due = Word(None, "지금")
                due.status = Status.LEARNING
                due.due = datetime.now(timezone.utc) - timedelta(minutes=1)
                soon = Word(None, "곧")
                soon.status = Status.LEARNING
                soon.due = datetime.now(timezone.utc) + timedelta(minutes=10)
                for word in (due, soon):
                    word_service._repository.save_word(user.user_id, word)
                    word_service._repository.save_doc_part_word(
                        DocPartWord(word, part, 1)
                    )

                result = word_service.get_due(user)

    assert result.word_id == due.word_id


def test_due_count_does_not_include_twenty_minute_lookahead(configured_settings):
    with UserService() as user_service:
        with DocumentService() as document_service:
            with WordService() as word_service:
                user = user_service.new_user("Reader")
                document = Document(None, "Reading", "Text", Language.KOREAN)
                document_service._repository.save_document(user.user_id, document)
                part = DocPart(None, "Text", 0, active=True)
                document_service._repository.save_doc_part(
                    document.document_id, part
                )
                soon = Word(None, "곧")
                soon.status = Status.LEARNING
                soon.due = datetime.now(timezone.utc) + timedelta(minutes=10)
                word_service._repository.save_word(user.user_id, soon)
                word_service._repository.save_doc_part_word(
                    DocPartWord(soon, part, 1)
                )

                assert word_service.get_due(user).word_id == soon.word_id
                assert word_service.count_due(user) == 0
                assert word_service.count_study_due(user) == 1


def test_record_response_schedules_and_persists_word(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            word = Word(None, "word")
            word_service._repository.save_word(user.user_id, word)

            word_service.record_response(user, word, Response.GOOD, 2400)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.LEARNING
            assert loaded.step == 1
            assert loaded.difficulty == pytest.approx(2.118103970459016)
            assert loaded.stability == pytest.approx(2.3065)
            assert loaded.due - loaded.last_reviewed == timedelta(minutes=10)
            reviews = word_service._repository.list_word_reviews(word.word_id)
            assert len(reviews) == 1
            assert reviews[0].response is Response.GOOD
            assert reviews[0].duration_ms == 2400

            word_service.record_response(user, word, Response.GOOD)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.REVIEW
            assert loaded.step is None
            assert loaded.due > loaded.last_reviewed
            assert len(word_service._repository.list_word_reviews(word.word_id)) == 2


def test_again_repeats_a_new_word_after_one_minute(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            word = Word(None, "word")
            word_service._repository.save_word(user.user_id, word)

            word_service.record_response(user, word, Response.AGAIN)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.LEARNING
            assert loaded.step == 0
            assert loaded.due - loaded.last_reviewed == timedelta(minutes=1)


def test_failed_review_enters_relearning(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            word = Word(None, "word")
            word.status = Status.REVIEW
            word.stability = 3.0
            word.difficulty = 5.0
            word.last_reviewed = datetime.now(timezone.utc) - timedelta(days=3)
            word.due = datetime.now(timezone.utc)
            word_service._repository.save_word(user.user_id, word)

            word_service.record_response(user, word, Response.AGAIN)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.RELEARNING
            assert loaded.step == 0
            assert loaded.due - loaded.last_reviewed == timedelta(minutes=10)


def test_mark_known_removes_word_from_review(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            word = Word(None, "word")
            word_service._repository.save_word(user.user_id, word)

            word_service.mark_known(user, word)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.KNOWN
            assert loaded.due is None
            assert word_service._repository.list_word_reviews(word.word_id) == []


def test_add_and_delete_user_meaning(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            other = user_service.new_user("Other Reader")
            word = Word(None, "단어")
            word_service._repository.save_word(user.user_id, word)

            meaning = word_service.add_user_meaning(
                user, word.word_id, " 사용자 정의 ", " user definition ", " mine "
            )

            assert meaning.korean_definition == "사용자 정의"
            assert meaning.english_definition == "user definition"
            assert meaning.gloss == "mine"
            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.user_meanings[0].user_meaning_id == meaning.user_meaning_id
            assert word_service.delete_user_meaning(
                other, meaning.user_meaning_id
            ) is False
            assert word_service.delete_user_meaning(
                user, meaning.user_meaning_id
            ) is True
            with pytest.raises(ValueError, match="required"):
                word_service.add_user_meaning(user, word.word_id, " ", "", "")


def test_record_response_requires_a_saved_word(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            user = user_service.new_user("Reader")
            with pytest.raises(ValueError, match="belong"):
                word_service.record_response(
                    user, Word(None, "word"), Response.GOOD
                )


def test_study_changes_require_word_ownership(configured_settings):
    with UserService() as user_service:
        with WordService() as word_service:
            owner = user_service.new_user("Owner")
            other = user_service.new_user("Other")
            word = Word(None, "단어")
            word_service._repository.save_word(owner.user_id, word)

            with pytest.raises(ValueError, match="belong"):
                word_service.record_response(other, word, Response.GOOD)
            with pytest.raises(ValueError, match="belong"):
                word_service.mark_known(other, word)

            loaded = word_service._repository.get_word(word.word_id)
            assert loaded.status is Status.NEW
