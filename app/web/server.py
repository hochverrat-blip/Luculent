from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask, jsonify, render_template, request

from app.domain import (
    DocPart,
    Document,
    Language,
    Response,
    UserWordMeaning,
    Word,
)
from app.services import DocumentService, UserService, WordService


def create_app() -> Flask:
    appl = Flask(__name__)

    @appl.route("/", methods=["GET"])
    def test_client():
        return render_template("index.html")

    @appl.route("/users", methods=["POST"])
    def create_user():
        data = request.get_json(silent=True)
        username = data.get("username", "") if isinstance(data, dict) else ""
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        try:
            with UserService() as user_service:
                user = user_service.new_user(username)
        except ValueError as error:
            return jsonify({"error": str(error)}), HTTPStatus.CONFLICT
        return (
            jsonify({"user": {"id": user.user_id, "username": user.name}}),
            HTTPStatus.CREATED,
        )

    @appl.route("/users", methods=["GET"])
    def get_users():
        with UserService() as user_service:
            users = user_service.get_users()
        return jsonify(
            {
                "users": [
                    {"id": user.user_id, "username": user.name}
                    for user in users
                ]
            }
        )

    @appl.route("/get-due-word", methods=["GET"])
    def get_due_word():
        username = request.args.get("username", "").strip()
        if not username:
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        exclude_value = request.args.get("exclude_word_id")
        try:
            exclude_word_id = None if exclude_value is None else int(exclude_value)
        except ValueError:
            return (
                jsonify({"error": "exclude_word_id must be an integer"}),
                HTTPStatus.BAD_REQUEST,
            )

        with WordService() as word_service:
            word = word_service.get_due(user, exclude_word_id)
        return jsonify({"word": None if word is None else _word_json(word)})

    @appl.route("/due-count", methods=["GET"])
    def get_due_count():
        username = request.args.get("username", "").strip()
        if not username:
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST
        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND
        with WordService() as word_service:
            count = word_service.count_due(user)
        return jsonify({"due_count": count})

    @appl.route("/documents", methods=["GET"])
    def get_documents():
        username = request.args.get("username", "").strip()
        if not username:
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        with DocumentService() as document_service:
            documents = document_service.get_documents(user)
        return jsonify({"documents": [_document_json(document) for document in documents]})

    @appl.route("/documents/<int:document_id>", methods=["DELETE"])
    def delete_document(document_id: int):
        data = request.get_json(silent=True)
        username = data.get("username", "") if isinstance(data, dict) else ""
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        with DocumentService() as document_service:
            document = next(
                (
                    item
                    for item in document_service.get_documents(user)
                    if item.document_id == document_id
                ),
                None,
            )
            if document is None:
                return jsonify({"error": "document not found"}), HTTPStatus.NOT_FOUND
            document_service.delete_document(user, document)
        return "", HTTPStatus.NO_CONTENT

    @appl.route("/lexicon-status", methods=["GET"])
    def get_lexicon_status():
        with DocumentService() as document_service:
            installed = document_service.is_lexicon_installed(Language.KOREAN)
        return jsonify({"installed": installed})

    @appl.route("/documents", methods=["POST"])
    def import_document():
        data = request.get_json(silent=True)
        username = (
            data.get("username", "")
            if isinstance(data, dict)
            else request.form.get("username", "")
        )
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        url = (
            data.get("url", "")
            if isinstance(data, dict)
            else request.form.get("url", "")
        )
        uploaded = request.files.get("file")
        if bool(isinstance(url, str) and url.strip()) == bool(
            uploaded and uploaded.filename
        ):
            return (
                jsonify({"error": "provide exactly one URL or text file"}),
                HTTPStatus.BAD_REQUEST,
            )

        try:
            with DocumentService() as document_service:
                if uploaded is None:
                    document = document_service.import_document_url(user, url.strip())
                else:
                    filename = Path(uploaded.filename.replace("\\", "/")).name
                    with TemporaryDirectory() as directory:
                        path = Path(directory, filename)
                        uploaded.save(path)
                        document = document_service.import_document_file(user, path)
        except (OSError, UnicodeError, ValueError) as error:
            return jsonify({"error": str(error)}), HTTPStatus.BAD_REQUEST
        return jsonify({"document": _document_json(document)}), HTTPStatus.CREATED

    @appl.route("/doc-parts/<int:doc_part_id>/activate", methods=["POST"])
    def activate_doc_part(doc_part_id: int):
        data = request.get_json(silent=True)
        username = data.get("username", "") if isinstance(data, dict) else ""
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        with DocumentService() as document_service:
            part = document_service.get_docpart(user, doc_part_id)
            if part is None:
                return jsonify({"error": "document part not found"}), HTTPStatus.NOT_FOUND
            document_service.activate_docpart(user, part)
        return jsonify({"doc_part": _doc_part_json(part)})

    @appl.route("/doc-parts/<int:doc_part_id>", methods=["GET"])
    def get_doc_part(doc_part_id: int):
        username = request.args.get("username", "").strip()
        if not username:
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST
        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND
        with DocumentService() as document_service:
            part = document_service.get_docpart(user, doc_part_id)
            if part is None:
                return jsonify({"error": "document part not found"}), HTTPStatus.NOT_FOUND
            marked_text = document_service.get_md_text(user, part.text)
        result = _doc_part_json(part)
        result["marked_text"] = marked_text
        return jsonify({"doc_part": result})

    @appl.route("/words/<int:word_id>/response", methods=["POST"])
    def record_word_response(word_id: int):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON body is required"}), HTTPStatus.BAD_REQUEST
        username = data.get("username", "")
        response_name = data.get("response", "")
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST
        if not isinstance(response_name, str):
            return jsonify({"error": "response is required"}), HTTPStatus.BAD_REQUEST
        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND
        with WordService() as word_service:
            word = word_service.get_word(user, word_id)
            if word is None:
                return jsonify({"error": "word not found"}), HTTPStatus.NOT_FOUND
            try:
                if response_name.casefold() == "known":
                    word_service.mark_known(word)
                else:
                    response = next(
                        response
                        for response in Response
                        if response.value.casefold() == response_name.casefold()
                    )
                    word_service.record_response(word, response, data.get("duration_ms"))
            except (StopIteration, TypeError, ValueError) as error:
                message = "invalid response" if isinstance(error, StopIteration) else str(error)
                return jsonify({"error": message}), HTTPStatus.BAD_REQUEST
            due_count = word_service.count_due(user)
        return jsonify({"word": _word_json(word), "due_count": due_count})

    @appl.route("/words/<int:word_id>/user-meanings", methods=["POST"])
    def add_user_meaning(word_id: int):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON body is required"}), HTTPStatus.BAD_REQUEST
        username = data.get("username", "")
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND

        try:
            with WordService() as word_service:
                meaning = word_service.add_user_meaning(
                    user,
                    word_id,
                    data.get("korean_definition", ""),
                    data.get("english_definition", ""),
                    data.get("gloss", ""),
                )
        except (AttributeError, ValueError) as error:
            return jsonify({"error": str(error)}), HTTPStatus.BAD_REQUEST
        return jsonify({"user_meaning": _user_meaning_json(meaning)}), HTTPStatus.CREATED

    @appl.route(
        "/user-meanings/<int:user_meaning_id>", methods=["DELETE"]
    )
    def delete_user_meaning(user_meaning_id: int):
        data = request.get_json(silent=True)
        username = data.get("username", "") if isinstance(data, dict) else ""
        if not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username is required"}), HTTPStatus.BAD_REQUEST

        with UserService() as user_service:
            user = user_service.get_user(username)
        if user is None:
            return jsonify({"error": "user not found"}), HTTPStatus.NOT_FOUND
        with WordService() as word_service:
            deleted = word_service.delete_user_meaning(user, user_meaning_id)
        if not deleted:
            return jsonify({"error": "user meaning not found"}), HTTPStatus.NOT_FOUND
        return "", HTTPStatus.NO_CONTENT

    return appl


def _document_json(document: Document) -> dict:
    return {
        "id": document.document_id,
        "title": document.title,
        "language": document.language.value,
        "imported": document.imported.isoformat(),
        "parts": [_doc_part_json(part) for part in document.doc_parts],
    }


def _doc_part_json(part: DocPart) -> dict:
    return {
        "id": part.doc_part_id,
        "position": part.position,
        "text": part.text,
        "readability": part.readability,
        "active": part.active,
    }


def _word_json(word: Word) -> dict:
    return {
        "id": word.word_id,
        "lemma": word.lemma,
        "language": word.language.value,
        "part_of_speech": word.pos.value,
        "status": word.status.value,
        "due": None if word.due is None else word.due.isoformat(),
        "meanings": [
            {
                "id": meaning.meaning_id,
                "korean_definition": meaning.korean_definition,
                "english_definition": meaning.english_definition,
                "gloss": meaning.gloss,
                "frequency": meaning.frequency.value,
                "labels": sorted(label.value for label in meaning.labels),
            }
            for meaning in word.meanings
        ],
        "user_meanings": [
            _user_meaning_json(meaning) for meaning in word.user_meanings
        ],
    }


def _user_meaning_json(meaning: UserWordMeaning) -> dict:
    return {
        "id": meaning.user_meaning_id,
        "word_id": meaning.word_id,
        "korean_definition": meaning.korean_definition,
        "english_definition": meaning.english_definition,
        "gloss": meaning.gloss,
    }


def run_server() -> None:
    create_app().run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    run_server()
