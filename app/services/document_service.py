from __future__ import annotations

from pathlib import Path

import spacy
from spacy.language import Language as SpacyLanguage
from spacy_language_detection import LanguageDetector

from app.domain import DocPart, Document, Language, User
from app.scraper import Scraper
from app.services.base_service import Service


SUPPORTED_DOCUMENT_LANGUAGES = {
    "en": Language.ENGLISH,
    "ko": Language.KOREAN,
}


def _create_language_detector(nlp, name):
    return LanguageDetector(seed=42)


if not SpacyLanguage.has_factory("language_detector"):
    SpacyLanguage.factory("language_detector", func=_create_language_detector)


_LANGUAGE_PIPELINE = spacy.blank("xx")
_LANGUAGE_PIPELINE.add_pipe("sentencizer")
_LANGUAGE_PIPELINE.add_pipe("language_detector")


class DocumentService(Service):
    
    def import_document_url(
        self,
        user: User,
        url: str,
    ) -> Document:
        page = Scraper.scrape(url)
        document = self._build_document(page.title, page.text)
        self._save_imported_document(user, document)
        return document

    def import_document_file(
        self,
        user: User,
        filename: str | Path,
    ) -> Document:
        path = Path(filename)
        document = self._build_document(
            path.stem,
            path.read_text(encoding="utf-8"),
        )
        self._save_imported_document(user, document)
        return document

    def _save_imported_document(self, user: User, document: Document) -> None:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before importing a document")
        self._repository.save_document_with_parts(user.user_id, document)

    def _build_document(self, title: str, text: str) -> Document:
        if not text.strip():
            raise ValueError("Cannot import an empty document")
        language_code = self._detect_language_code(text).lower()
        if language_code not in SUPPORTED_DOCUMENT_LANGUAGES:
            raise ValueError(f"Unsupported document language: {language_code}")
        language = SUPPORTED_DOCUMENT_LANGUAGES[language_code]
        document = Document(None, title, text, language)
        document.doc_parts.extend(
            DocPart(None, part_text, position)
            for position, part_text in enumerate(self._split_text(text))
        )
        return document

    @staticmethod
    def _split_text(text: str) -> list[str]:
        sentences = [
            " ".join(sentence.text.split())
            for sentence in _LANGUAGE_PIPELINE(text).sents
            if sentence.text.strip()
        ]
        parts: list[str] = []
        current_sentences: list[str] = []
        current_word_count = 0
        for sentence in sentences:
            sentence_word_count = len(sentence.split())
            if current_sentences and current_word_count + sentence_word_count > 300:
                parts.append(" ".join(current_sentences))
                current_sentences = []
                current_word_count = 0
            current_sentences.append(sentence)
            current_word_count += sentence_word_count
        if current_sentences:
            parts.append(" ".join(current_sentences))
        return parts

    @staticmethod
    def _detect_language_code(text: str) -> str:
        detection = _LANGUAGE_PIPELINE(text)._.language
        return detection["language"]
