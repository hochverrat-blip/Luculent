from app.document import *


class User:
    def __init__(
        self,
        user_id: int,
        name: str,
        created: Optional[date] = None
    ):
        self._user_id = user_id
        self._name = name
        self._created = created or date.today()

        self._documents: list[Document] = []
        self._words: list[Word] = []

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def created(self) -> date:
        return self._created

    @property
    def documents(self) -> list[Document]:
        return self._documents

    @property
    def words(self) -> list[Word]:
        return self._words
