from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from app.domain.enums import Language

if TYPE_CHECKING:
    from app.domain.word import DocPartWord

class Document:
    def __init__(
        self,
        document_id: int,
        title: str,
        text: str,
        language: Language,
        imported: Optional[date] = None
    ):
        self._document_id = document_id
        self._title = title
        self._text = text
        self._imported = imported or date.today()
        self._language = language

        self._doc_parts: list[DocPart] = []

    @property
    def document_id(self) -> int:
        return self._document_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def text(self) -> str:
        return self._text

    @property
    def imported(self) -> date:
        return self._imported

    @property
    def language(self) -> Language:
        return self._language

    @property
    def doc_parts(self) -> list[DocPart]:
        return self._doc_parts


class DocPart:
    def __init__(
        self,
        doc_part_id: int,
        text: str,
        position: int,
        readability: float = 0.0,
        active: bool = False
    ):
        self._doc_part_id = doc_part_id
        self._text = text
        self._position = position
        self._readability = readability
        self._active = active

        self._doc_part_words: list[DocPartWord] = []

    @property
    def doc_part_id(self) -> int:
        return self._doc_part_id

    @property
    def text(self) -> str:
        return self._text

    @property
    def position(self) -> int:
        return self._position

    @property
    def readability(self) -> float:
        return self._readability

    @readability.setter
    def readability(self, value: float) -> None:
        self._readability = value

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    @property
    def doc_part_words(self) -> list[DocPartWord]:
        return self._doc_part_words
