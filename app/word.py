from __future__ import annotations

from typing import Optional
from app.enums import *
from app.document import *

class Word:
    def __init__(
        self,
        word_id: int,
        lemma: str = "",
        definition: str = "",
        language: Language = Language.KOREAN,
        pos: POS = POS.NOUN
    ):
        self._word_id = word_id
        self._lemma = lemma
        self._definition = definition
        self._due: Optional[date] = None
        self._difficulty = 0.0
        self._stability = 0.0
        self._image_path: Optional[str] = None
        self._status = Status.NEW
        self._last_reviewed: Optional[date] = None
        self._pos = pos
        self._language = language

        self._doc_part_words: list[DocPartWord] = []

    @property
    def word_id(self) -> int:
        return self._word_id

    @property
    def lemma(self) -> str:
        return self._lemma

    @lemma.setter
    def lemma(self, value: str) -> None:
        self._lemma = value

    @property
    def definition(self) -> str:
        return self._definition

    @definition.setter
    def definition(self, value: str) -> None:
        self._definition = value

    @property
    def due(self) -> Optional[date]:
        return self._due

    @due.setter
    def due(self, value: Optional[date]) -> None:
        self._due = value

    @property
    def difficulty(self) -> float:
        return self._difficulty

    @difficulty.setter
    def difficulty(self, value: float) -> None:
        self._difficulty = value

    @property
    def stability(self) -> float:
        return self._stability

    @stability.setter
    def stability(self, value: float) -> None:
        self._stability = value

    @property
    def image_path(self) -> Optional[str]:
        return self._image_path

    @image_path.setter
    def image_path(self, value: Optional[str]) -> None:
        self._image_path = value

    @property
    def status(self) -> Status:
        return self._status

    @status.setter
    def status(self, value: Status) -> None:
        self._status = value

    @property
    def last_reviewed(self) -> Optional[date]:
        return self._last_reviewed

    @last_reviewed.setter
    def last_reviewed(self, value: Optional[date]) -> None:
        self._last_reviewed = value

    @property
    def pos(self) -> POS:
        return self._pos

    @pos.setter
    def pos(self, value: POS) -> None:
        self._pos = value

    @property
    def language(self) -> Language:
        return self._language

    @property
    def doc_part_words(self) -> list[DocPartWord]:
        return self._doc_part_words


class DocPartWord:
    def __init__(
        self,
        word: Word,
        doc_part: DocPart,
        occurrences: int
    ):
        self._word = word
        self._doc_part = doc_part
        self._occurrences = occurrences

    @property
    def word(self) -> Word:
        return self._word

    @property
    def doc_part(self) -> DocPart:
        return self._doc_part

    @property
    def occurrences(self) -> int:
        return self._occurrences