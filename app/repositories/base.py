from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

from app.domain.document import DocPart, Document
from app.domain.enums import Language, POS
from app.domain.user import User
from app.domain.word import (
    DocPartWord,
    UserWordMeaning,
    Word,
    WordMeaning,
    WordReview,
)


class Repository(ABC):
    """Database-neutral repository interface"""

    @abstractmethod
    def initialize(self) -> None:
        """Create the database structures"""

    @abstractmethod
    def save_user(self, user: User) -> None:
        """Insert or update a user, assigning a generated ID when its ID is None"""

    @abstractmethod
    def get_user(self, user_id: int) -> User | None:
        """Return a user, or None when the ID does not exist"""

    @abstractmethod
    def get_user_by_name(self, name: str) -> User | None:
        """Return the user with the given name, or None when it does not exist"""

    @abstractmethod
    def list_users(self) -> list[User]:
        """Return all users in name and ID order"""

    @abstractmethod
    def delete_user(self, user_id: int) -> bool:
        """Delete the user with the given ID and return whether it existed"""

    @abstractmethod
    def save_document(self, user_id: int, document: Document) -> None:
        """Insert or update a document, assigning a generated ID when needed"""

    @abstractmethod
    def save_document_with_parts(self, user_id: int, document: Document) -> None:
        """Save a document and its parts as one transaction"""

    @abstractmethod
    def save_document_import(
        self,
        user_id: int,
        document: Document,
        associations: list[DocPartWord],
    ) -> None:
        """Save an imported document, words, and associations as one transaction"""

    @abstractmethod
    def get_document(self, document_id: int) -> Document | None:
        """Return a document, or None when the ID does not exist"""

    @abstractmethod
    def list_documents(self, user_id: int) -> list[Document]:
        """Return a user's documents in import and ID order"""

    @abstractmethod
    def delete_document(self, user_id: int, document_id: int) -> bool:
        """Delete a user's document and return whether it existed"""

    @abstractmethod
    def save_doc_part(self, document_id: int, doc_part: DocPart) -> None:
        """Insert or update a document part, assigning a generated ID when needed"""

    @abstractmethod
    def list_doc_parts(self, document_id: int) -> list[DocPart]:
        """Return document parts in reading order"""

    @abstractmethod
    def get_users_doc_part(self, user_id: int, doc_part_id: int) -> DocPart | None:
        """Return a document part only when its document belongs to the user"""

    @abstractmethod
    def activate_doc_part(self, user_id: int, doc_part_id: int) -> None:
        """Make one of a user's document parts their only active part"""

    @abstractmethod
    def save_word(self, user_id: int, word: Word) -> None:
        """Insert or update a word, assigning a generated ID when needed"""

    @abstractmethod
    def get_word(self, word_id: int) -> Word | None:
        """Return a word, or None when the ID does not exist"""

    @abstractmethod
    def get_user_word(self, user_id: int, word_id: int) -> Word | None:
        """Return a word only when it belongs to the user"""

    @abstractmethod
    def list_words(self, user_id: int) -> list[Word]:
        """Return a user's words in ID order"""

    @abstractmethod
    def list_words_by_lemmas(
        self, user_id: int, language: Language, lemmas: set[str]
    ) -> list[Word]:
        """Return a user's words matching the language and lemmas"""

    @abstractmethod
    def update_word_study(self, word: Word) -> None:
        """Update scheduling fields for an existing word"""

    @abstractmethod
    def record_word_review(self, word: Word, review: WordReview) -> None:
        """Update a word and append its review as one transaction"""

    @abstractmethod
    def list_word_reviews(self, word_id: int) -> list[WordReview]:
        """Return a word's reviews in chronological and ID order"""

    @abstractmethod
    def save_word_meaning(self, word_id: int, meaning: WordMeaning) -> None:
        """Insert or update a meaning and its labels"""

    @abstractmethod
    def list_word_meanings(self, word_id: int) -> list[WordMeaning]:
        """Return a word's meanings in display order"""

    @abstractmethod
    def save_user_word_meaning(
        self, user_id: int, meaning: UserWordMeaning
    ) -> None:
        """Insert or update a user-owned meaning for one of their words"""

    @abstractmethod
    def list_user_word_meanings(self, word_id: int) -> list[UserWordMeaning]:
        """Return a word's user meanings in display order"""

    @abstractmethod
    def delete_user_word_meaning(self, user_id: int, user_meaning_id: int) -> bool:
        """Delete a user meaning only when it belongs to the user"""

    @abstractmethod
    def get_lexicon_version(self, source: str) -> str | None:
        """Return the installed version for a lexicon source"""

    @abstractmethod
    def install_lexicon(
        self,
        source: str,
        version: str,
        checksum: str,
        meanings: Iterable[tuple[str, Language, POS, WordMeaning]],
    ) -> None:
        """Replace a source's shared lexicon meanings as one transaction"""

    @abstractmethod
    def get_due_word_in_active_parts(
        self, user_id: int, due_at: datetime, exclude_word_id: int | None = None
    ) -> Word | None:
        """Return the next reviewable word due in a user's active document parts"""

    @abstractmethod
    def count_due_words_in_active_parts(
        self, user_id: int, due_at: datetime
    ) -> int:
        """Count reviewable words due in a user's active document parts"""

    @abstractmethod
    def save_doc_part_word(self, association: DocPartWord) -> None:
        """Insert or update the occurrence count linking a part and word"""

    @abstractmethod
    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        """Return all word associations for a document part"""

    @abstractmethod
    def list_users_doc_part_words(self, user_id: int) -> list[DocPartWord]:
        """Return lightweight word associations for all of a user's document parts"""

    @abstractmethod
    def close(self) -> None:
        """Release database resources"""

    def __enter__(self) -> Repository:
        self.initialize()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
