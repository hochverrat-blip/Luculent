from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import spacy
from kiwipiepy import Kiwi
from spacy.language import Language as SpacyLanguage
from spacy_language_detection import LanguageDetector

from app.domain import DocPart, DocPartWord, Document, Language, POS, User, Word
from app.lexicon import ensure_lexicon
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

_CONTENT_PIPELINES = {
    Language.ENGLISH: spacy.load("en_core_web_sm", disable=["parser", "ner"]),
}

_KOREAN_PIPELINE = Kiwi()

_CONTENT_POS = {
    "ADJ": POS.ADJECTIVE,
    "ADV": POS.ADVERB,
    "NOUN": POS.NOUN,
    "PROPN": POS.NOUN,
    "VERB": POS.VERB,
}

_KOREAN_CONTENT_POS = {
    "MAG": POS.ADVERB,
    "NNG": POS.NOUN,
    "NNP": POS.NOUN,
    "VA": POS.ADJECTIVE,
    "VV": POS.VERB,
}


class DocumentService(Service):
    
    def import_document_url(
        self,
        user: User,
        url: str,
    ) -> Document:
        page = Scraper.scrape(url)
        document = self._build_document(page.title, page.text)
        self._import_words(user, document)
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
        self._import_words(user, document)
        return document

    def get_documents(self, user: User) -> list[Document]:
        self._require_saved_user(user)
        return self._repository.list_documents(user.user_id)

    def _import_words(self, user: User, document: Document) -> None:
        self._require_saved_user(user)
        ensure_lexicon(self._repository, document.language)
        part_words: list[Counter[tuple[str, POS]]] = []
        identities: set[tuple[str, POS]] = set()
        for doc_part in document.doc_parts:
            counts: Counter[tuple[str, POS]] = Counter()
            for lemma, pos in self._content_words(doc_part.text, document.language):
                identity = (lemma, pos)
                counts[identity] += 1
                identities.add(identity)
            part_words.append(counts)

        words = {
            (word.lemma, word.pos): word
            for word in self._repository.list_words_by_lemmas(
                user.user_id,
                document.language,
                {lemma for lemma, pos in identities},
            )
        }
        for identity in identities:
            if identity not in words:
                lemma, pos = identity
                words[identity] = Word(
                    None, lemma=lemma, language=document.language, pos=pos
                )

        associations: list[DocPartWord] = []
        for doc_part, counts in zip(document.doc_parts, part_words):
            for identity, occurrences in counts.items():
                associations.append(
                    DocPartWord(words[identity], doc_part, occurrences)
                )
        self._repository.save_document_import(
            user.user_id, document, associations
        )

    @staticmethod
    def _content_words(text: str, language: Language) -> Iterator[tuple[str, POS]]:
        if language is Language.KOREAN:
            tokens = _KOREAN_PIPELINE.tokenize(text, typos="basic")
            index = 0
            while index < len(tokens):
                token = tokens[index]
                tag = token.tag.split("-", 1)[0]
                if tag in {"NNG", "NNP", "XR"} and index + 1 < len(tokens):
                    suffix = tokens[index + 1]
                    suffix_tag = suffix.tag.split("-", 1)[0]
                    if suffix_tag in {"XSA", "XSV"}:
                        pos = POS.ADJECTIVE if suffix_tag == "XSA" else POS.VERB
                        yield f"{token.form}{suffix.form}다".casefold(), pos
                        index += 2
                        continue

                pos = _KOREAN_CONTENT_POS.get(tag)
                if pos is None:
                    index += 1
                    continue
                lemma = token.form.casefold()
                if pos in {POS.ADJECTIVE, POS.VERB}:
                    lemma += "다"
                yield lemma, pos
                index += 1
            return

        for token in _CONTENT_PIPELINES[language](text):
            pos = _CONTENT_POS.get(token.pos_)
            lemma = token.lemma_.strip().casefold()
            if pos is not None and token.is_alpha and lemma:
                yield lemma, pos

    def _require_saved_user(self, user: User) -> None:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before accessing documents")

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
