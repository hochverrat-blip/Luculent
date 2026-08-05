from datetime import date
from typing import Optional

from app.domain.enums import Language


SUPPORTED_NATIVE_LANGUAGES = frozenset({Language.ENGLISH})


class User:
    def __init__(
        self,
        user_id: int | None,
        name: str,
        created: Optional[date] = None,
        native_language: Language = Language.ENGLISH,
    ):
        if native_language not in SUPPORTED_NATIVE_LANGUAGES:
            raise ValueError("Only English is currently supported as a native language")
        self._user_id = user_id
        self._name = name
        self._created = created or date.today()
        self._native_language = native_language

    def _assign_id(self, user_id: int) -> None:
        self._user_id = user_id

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def created(self) -> date:
        return self._created

    @property
    def native_language(self) -> Language:
        return self._native_language
