from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from typing import Optional

from app.domain.enums import Language, MeaningFrequency, MeaningLabel, POS, Status

if TYPE_CHECKING:
    from app.domain.document import DocPart

class Word:
    def __init__(
        self,
        word_id: int | None,
        lemma: str = "",
        language: Language = Language.KOREAN,
        pos: POS = POS.NOUN
    ):
        self._word_id = word_id
        self._lemma = lemma
        self._due: Optional[date] = None
        self._difficulty = 0.0
        self._stability = 0.0
        self._image_path: Optional[str] = None
        self._status = Status.NEW
        self._last_reviewed: Optional[date] = None
        self._pos = pos
        self._language = language

        self._doc_part_words: list[DocPartWord] = []
        self._meanings: list[WordMeaning] = []

    def _assign_id(self, word_id: int) -> None:
        self._word_id = word_id

    @property
    def word_id(self) -> int | None:
        return self._word_id

    @property
    def lemma(self) -> str:
        return self._lemma

    @lemma.setter
    def lemma(self, value: str) -> None:
        self._lemma = value

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

    @property
    def meanings(self) -> list[WordMeaning]:
        return self._meanings


class WordMeaning:
    def __init__(
        self,
        meaning_id: int | None,
        korean_definition: str = "",
        english_definition: str = "",
        gloss: str = "",
        frequency: MeaningFrequency = MeaningFrequency.COMMON,
        labels: set[MeaningLabel] | None = None,
        display_order: int = 0,
    ):
        self._meaning_id = meaning_id
        self._korean_definition = korean_definition
        self._english_definition = english_definition
        self._gloss = gloss
        self._frequency = frequency
        self._labels = set() if labels is None else set(labels)
        self._display_order = display_order

    def _assign_id(self, meaning_id: int) -> None:
        self._meaning_id = meaning_id

    @property
    def meaning_id(self) -> int | None:
        return self._meaning_id

    @property
    def korean_definition(self) -> str:
        return self._korean_definition

    @korean_definition.setter
    def korean_definition(self, value: str) -> None:
        self._korean_definition = value

    @property
    def english_definition(self) -> str:
        return self._english_definition

    @english_definition.setter
    def english_definition(self, value: str) -> None:
        self._english_definition = value

    @property
    def gloss(self) -> str:
        return self._gloss

    @gloss.setter
    def gloss(self, value: str) -> None:
        self._gloss = value

    @property
    def frequency(self) -> MeaningFrequency:
        return self._frequency

    @frequency.setter
    def frequency(self, value: MeaningFrequency) -> None:
        self._frequency = value

    @property
    def labels(self) -> set[MeaningLabel]:
        return self._labels

    @property
    def display_order(self) -> int:
        return self._display_order

    @display_order.setter
    def display_order(self, value: int) -> None:
        self._display_order = value


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
