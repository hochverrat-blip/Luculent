from pathlib import Path

import pytest

import app.settings as settings_module
import app.services.document_service as document_service_module
from app.domain import (
    DocPart,
    DocPartWord,
    Language,
    POS,
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
        user_service.new_user("Vance")


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
            with pytest.raises(ValueError, match="saved"):
                document_service.get_documents(User(None, "Unsaved"))


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


def test_get_learning_returns_learning_words_in_active_parts(
    configured_settings, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "en"),
    )
    path = tmp_path / "reading.txt"
    path.write_text("Some document text", encoding="utf-8")

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

                included = Word(None, "included")
                included.status = Status.LEARNING
                not_learning = Word(None, "new")
                inactive = Word(None, "inactive")
                inactive.status = Status.LEARNING
                word_service._repository.save_word(user.user_id, included)
                word_service._repository.save_word(user.user_id, not_learning)
                word_service._repository.save_word(user.user_id, inactive)
                word_service._repository.save_doc_part_word(
                    DocPartWord(included, active_part, 1)
                )
                word_service._repository.save_doc_part_word(
                    DocPartWord(not_learning, active_part, 1)
                )
                word_service._repository.save_doc_part_word(
                    DocPartWord(inactive, inactive_part, 1)
                )

                learning = word_service.get_learning(user)

    assert [word.word_id for word in learning] == [included.word_id]


def test_get_learning_requires_a_saved_user(configured_settings):
    with WordService() as word_service:
        with pytest.raises(ValueError, match="saved"):
            word_service.get_learning(User(None, "Reader"))
