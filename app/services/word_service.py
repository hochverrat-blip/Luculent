from app.domain import User, Word
from app.services.base_service import Service


class WordService(Service):
    def get_learning(self, user: User) -> list[Word]:
        if user.user_id is None:
            raise ValueError("User must be saved before getting learning words")

        return self._repository.list_learning_words_in_active_parts(user.user_id)
