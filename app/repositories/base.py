from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.document import DocPart, Document
from app.domain.user import User
from app.domain.word import DocPartWord, Word


class Repository(ABC):
    """Database-neutral persistence boundary for Luculent domain objects."""

    @abstractmethod
    def initialize(self) -> None:
        """Create the database structures required by the app."""

    @abstractmethod
    def save_user(self, user: User) -> None:
        """Insert or update a user."""

    @abstractmethod
    def get_user(self, user_id: int) -> User | None:
        """Return a user, or None when the ID does not exist."""

    @abstractmethod
    def save_document(self, user_id: int, document: Document) -> None:
        """Insert or update a document owned by a user."""

    @abstractmethod
    def get_document(self, document_id: int) -> Document | None:
        """Return a document, or None when the ID does not exist."""

    @abstractmethod
    def list_documents(self, user_id: int) -> list[Document]:
        """Return a user's documents in import and ID order."""

    @abstractmethod
    def save_doc_part(self, document_id: int, doc_part: DocPart) -> None:
        """Insert or update a document part."""

    @abstractmethod
    def list_doc_parts(self, document_id: int) -> list[DocPart]:
        """Return document parts in reading order."""

    @abstractmethod
    def save_word(self, user_id: int, word: Word) -> None:
        """Insert or update a word owned by a user."""

    @abstractmethod
    def get_word(self, word_id: int) -> Word | None:
        """Return a word, or None when the ID does not exist."""

    @abstractmethod
    def list_words(self, user_id: int) -> list[Word]:
        """Return a user's words in ID order."""

    @abstractmethod
    def save_doc_part_word(self, association: DocPartWord) -> None:
        """Insert or update the occurrence count linking a part and word."""

    @abstractmethod
    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        """Return all word associations for a document part."""

    @abstractmethod
    def close(self) -> None:
        """Release database resources."""

    def __enter__(self) -> Repository:
        self.initialize()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
