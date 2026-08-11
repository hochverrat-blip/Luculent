from datetime import datetime, timezone
from io import BytesIO

import app.settings as settings_module
import app.services.document_service as document_service_module
from app.domain import (
    DocPart,
    DocPartWord,
    Document,
    Language,
    POS,
    Status,
    User,
    Word,
)
from app.domain.word import WordMeaning
from app.lexicon import KOREAN_LEXICON_SOURCE
from app.repositories.factory import create_repository
from app.scraper import ScrapedPage, Scraper
from app.services import DocumentService
from app.web import create_app


def _configure_database(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.txt"
    settings_path.write_text(
        f"database=sqlite\nsqlite_path={tmp_path / 'web.db'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)


def test_get_due_word_returns_next_word_with_meanings(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        user = User(None, "Reader")
        repository.save_user(user)
        document = Document(None, "Reading", "Text", Language.KOREAN)
        repository.save_document(user.user_id, document)
        part = DocPart(None, "Text", 0, active=True)
        repository.save_doc_part(document.document_id, part)
        word = Word(None, "단어", Language.KOREAN, POS.NOUN)
        word.status = Status.REVIEW
        word.due = datetime.now(timezone.utc)
        word.meanings.append(
            WordMeaning(
                None,
                korean_definition="말이나 글의 단위.",
                english_definition="A unit of speech or writing.",
                gloss="word",
            )
        )
        repository.save_word(user.user_id, word)
        repository.save_word_meaning(word.word_id, word.meanings[0])
        repository.save_doc_part_word(DocPartWord(word, part, 1))

    response = create_app().test_client().get(
        "/get-due-word", query_string={"username": "Reader"}
    )

    assert response.status_code == 200
    assert response.json["word"] == {
        "id": word.word_id,
        "lemma": "단어",
        "language": "Korean",
        "part_of_speech": "Noun",
        "status": "Review",
        "due": word.due.isoformat(),
        "meanings": [
            {
                "id": word.meanings[0].meaning_id,
                "korean_definition": "말이나 글의 단위.",
                "english_definition": "A unit of speech or writing.",
                "gloss": "word",
                "frequency": "Common",
                "labels": [],
            }
        ],
        "user_meanings": [],
    }


def test_get_due_word_returns_null_when_nothing_is_due(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        repository.save_user(User(None, "Reader"))

    response = create_app().test_client().get(
        "/get-due-word", query_string={"username": "Reader"}
    )

    assert response.status_code == 200
    assert response.json == {"word": None}


def test_get_due_word_validates_username(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    client = create_app().test_client()

    missing = client.get("/get-due-word")
    unknown = client.get(
        "/get-due-word", query_string={"username": "Missing"}
    )
    client.post("/users", json={"username": "Reader"})
    bad_exclusion = client.get(
        "/get-due-word",
        query_string={"username": "Reader", "exclude_word_id": "word"},
    )

    assert missing.status_code == 400
    assert missing.json == {"error": "username is required"}
    assert unknown.status_code == 404
    assert unknown.json == {"error": "user not found"}
    assert bad_exclusion.status_code == 400


def test_user_interface_is_available(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)

    client = create_app().test_client()
    response = client.get("/")
    favicon = client.get("/static/favicon.svg")

    assert response.status_code == 200
    assert favicon.status_code == 200
    assert b'href="/static/favicon.svg"' in response.data
    assert b"Read what you want." in response.data
    assert b'id="user-screen"' in response.data
    assert b'id="study-card"' in response.data
    assert b'<details class="add-meaning">' in response.data
    assert b"Preparing this reading" in response.data
    assert b'id="previous-part"' in response.data
    assert b'id="next-part"' in response.data


def test_lexicon_status_reports_installation(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    client = create_app().test_client()

    missing = client.get("/lexicon-status")
    with create_repository() as repository:
        repository.install_lexicon(
            KOREAN_LEXICON_SOURCE, "1", "checksum", []
        )
    installed = client.get("/lexicon-status")

    assert missing.json == {"installed": False}
    assert installed.json == {"installed": True}


def test_create_user_supports_fresh_database(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    client = create_app().test_client()

    created = client.post("/users", json={"username": " Reader "})
    duplicate = client.post("/users", json={"username": "Reader"})
    missing = client.post("/users", json={})
    users = client.get("/users")

    assert created.status_code == 201
    assert created.json["user"]["username"] == "Reader"
    assert isinstance(created.json["user"]["id"], int)
    assert duplicate.status_code == 409
    assert duplicate.json == {"error": "User already exists: Reader"}
    assert missing.status_code == 400
    assert missing.json == {"error": "username is required"}
    assert users.json == {
        "users": [{"id": created.json["user"]["id"], "username": "Reader"}]
    }


def test_import_file_and_list_documents_with_parts(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "ko"),
    )
    monkeypatch.setattr(
        document_service_module, "ensure_lexicon", lambda *args: None
    )
    client = create_app().test_client()
    client.post("/users", json={"username": "Reader"})

    imported = client.post(
        "/documents",
        data={
            "username": "Reader",
            "file": (BytesIO("고양이가 먹었다.".encode()), "사라진 열쇠.txt"),
        },
        content_type="multipart/form-data",
    )
    listed = client.get("/documents", query_string={"username": "Reader"})

    assert imported.status_code == 201
    assert imported.json["document"]["title"] == "사라진 열쇠"
    assert imported.json["document"]["parts"][0]["text"] == "고양이가 먹었다."
    assert listed.status_code == 200
    assert listed.json == {"documents": [imported.json["document"]]}


def test_delete_document_keeps_the_users_words(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        reader = User(None, "Reader")
        other_reader = User(None, "Other Reader")
        repository.save_user(reader)
        repository.save_user(other_reader)
        document = Document(None, "Finished", "Word.", Language.ENGLISH)
        repository.save_document(reader.user_id, document)
        part = DocPart(None, "Word.", 0)
        repository.save_doc_part(document.document_id, part)
        word = Word(None, "word")
        repository.save_word(reader.user_id, word)
        repository.save_doc_part_word(DocPartWord(word, part, 1))
        document_id = document.document_id
        part_id = part.doc_part_id
        word_id = word.word_id

    client = create_app().test_client()
    not_owned = client.delete(
        f"/documents/{document_id}", json={"username": "Other Reader"}
    )
    deleted = client.delete(
        f"/documents/{document_id}", json={"username": "Reader"}
    )

    assert not_owned.status_code == 404
    assert deleted.status_code == 204
    with create_repository() as repository:
        assert repository.get_document(document_id) is None
        assert repository.list_doc_part_words(part_id) == []
        assert [stored.word_id for stored in repository.list_words(reader.user_id)] == [
            word_id
        ]


def test_import_document_url(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    monkeypatch.setattr(
        DocumentService,
        "_detect_language_code",
        staticmethod(lambda text: "ko"),
    )
    monkeypatch.setattr(
        document_service_module, "ensure_lexicon", lambda *args: None
    )
    monkeypatch.setattr(
        Scraper,
        "scrape",
        staticmethod(lambda url: ScrapedPage("기사", "고양이가 먹었다.")),
    )
    client = create_app().test_client()
    client.post("/users", json={"username": "Reader"})

    response = client.post(
        "/documents",
        json={"username": "Reader", "url": "https://example.com/article"},
    )

    assert response.status_code == 201
    assert response.json["document"]["title"] == "기사"


def test_document_endpoints_validate_request(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    client = create_app().test_client()
    client.post("/users", json={"username": "Reader"})

    assert client.get("/documents").status_code == 400
    assert client.get(
        "/documents", query_string={"username": "Missing"}
    ).status_code == 404
    missing_source = client.post("/documents", json={"username": "Reader"})
    both_sources = client.post(
        "/documents",
        data={
            "username": "Reader",
            "url": "https://example.com",
            "file": (BytesIO(b"text"), "reading.txt"),
        },
        content_type="multipart/form-data",
    )

    assert missing_source.status_code == 400
    assert missing_source.json == {
        "error": "provide exactly one URL or text file"
    }
    assert both_sources.status_code == 400


def test_activate_doc_part_makes_its_words_due(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        user = User(None, "Reader")
        repository.save_user(user)
        document = Document(None, "Reading", "Text", Language.KOREAN)
        repository.save_document(user.user_id, document)
        part = DocPart(None, "단어", 0)
        repository.save_doc_part(document.document_id, part)
        word = Word(None, "단어", Language.KOREAN, POS.NOUN)
        repository.save_word(user.user_id, word)
        repository.save_doc_part_word(DocPartWord(word, part, 1))
    client = create_app().test_client()

    before = client.get(
        "/get-due-word", query_string={"username": "Reader"}
    )
    activated = client.post(
        f"/doc-parts/{part.doc_part_id}/activate",
        json={"username": "Reader"},
    )
    after = client.get(
        "/get-due-word", query_string={"username": "Reader"}
    )
    count = client.get("/due-count", query_string={"username": "Reader"})
    known = client.post(
        f"/words/{word.word_id}/response",
        json={"username": "Reader", "response": "Known", "duration_ms": 50},
    )

    assert before.json == {"word": None}
    assert activated.status_code == 200
    assert activated.json["doc_part"]["active"] is True
    assert after.json["word"]["id"] == word.word_id
    assert count.json == {"due_count": 1}
    assert known.status_code == 200
    assert known.json["word"]["status"] == "Known"
    assert known.json["due_count"] == 0


def test_activate_doc_part_rejects_another_users_part(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        reader = User(None, "Reader")
        other = User(None, "Other")
        repository.save_user(reader)
        repository.save_user(other)
        document = Document(None, "Other", "Text", Language.KOREAN)
        repository.save_document(other.user_id, document)
        part = DocPart(None, "Text", 0)
        repository.save_doc_part(document.document_id, part)

    response = create_app().test_client().post(
        f"/doc-parts/{part.doc_part_id}/activate",
        json={"username": "Reader"},
    )

    assert response.status_code == 404
    assert response.json == {"error": "document part not found"}


def test_add_and_delete_user_meaning_without_changing_lexicon_meanings(
    tmp_path, monkeypatch
):
    _configure_database(tmp_path, monkeypatch)
    with create_repository() as repository:
        user = User(None, "Reader")
        repository.save_user(user)
        document = Document(None, "Reading", "Text", Language.KOREAN)
        repository.save_document(user.user_id, document)
        part = DocPart(None, "단어", 0, active=True)
        repository.save_doc_part(document.document_id, part)
        word = Word(None, "단어", Language.KOREAN, POS.NOUN)
        repository.save_word(user.user_id, word)
        repository.save_word_meaning(word.word_id, WordMeaning(None, gloss="word"))
        repository.save_doc_part_word(DocPartWord(word, part, 1))
    client = create_app().test_client()

    added = client.post(
        f"/words/{word.word_id}/user-meanings",
        json={
            "username": "Reader",
            "korean_definition": "내 뜻",
            "english_definition": "my meaning",
            "gloss": "mine",
        },
    )
    due = client.get("/get-due-word", query_string={"username": "Reader"})
    deleted = client.delete(
        f"/user-meanings/{added.json['user_meaning']['id']}",
        json={"username": "Reader"},
    )
    due_after_delete = client.get(
        "/get-due-word", query_string={"username": "Reader"}
    )

    assert added.status_code == 201
    assert due.json["word"]["meanings"][0]["gloss"] == "word"
    assert due.json["word"]["user_meanings"][0]["gloss"] == "mine"
    assert deleted.status_code == 204
    assert due_after_delete.json["word"]["meanings"][0]["gloss"] == "word"
    assert due_after_delete.json["word"]["user_meanings"] == []
