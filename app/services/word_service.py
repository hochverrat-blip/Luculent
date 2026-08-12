from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

from app.domain import (
    Response,
    Status,
    User,
    UserWordMeaning,
    Word,
    WordReview,
)
from app.services.base_service import Service


_SCHEDULER = Scheduler()
_READABILITY_HORIZON = timedelta(days=7)
_DUE_LOOKAHEAD = timedelta(minutes=20)

_RATINGS = {
    Response.AGAIN: Rating.Again,
    Response.HARD: Rating.Hard,
    Response.GOOD: Rating.Good,
    Response.EASY: Rating.Easy,
}

_FSRS_STATES = {
    Status.NEW: State.Learning,
    Status.LEARNING: State.Learning,
    Status.REVIEW: State.Review,
    Status.RELEARNING: State.Relearning,
}

_WORD_STATUSES = {
    State.Learning: Status.LEARNING,
    State.Review: Status.REVIEW,
    State.Relearning: Status.RELEARNING,
}


class WordService(Service):

    def get_word(self, user: User, word_id: int) -> Word | None:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before getting a word")
        return self._repository.get_user_word(user.user_id, word_id)

    def add_user_meaning(
        self,
        user: User,
        word_id: int,
        korean_definition: str = "",
        english_definition: str = "",
        gloss: str = "",
    ) -> UserWordMeaning:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before adding a meaning")
        values = tuple(
            value.strip()
            for value in (korean_definition, english_definition, gloss)
        )
        if not any(values):
            raise ValueError("At least one definition or gloss is required")
        meaning = UserWordMeaning(None, word_id, *values)
        self._repository.save_user_word_meaning(user.user_id, meaning)
        return meaning

    def delete_user_meaning(self, user: User, user_meaning_id: int) -> bool:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before deleting a meaning")
        return self._repository.delete_user_word_meaning(
            user.user_id, user_meaning_id
        )

    def get_due(
        self, user: User, exclude_word_id: int | None = None
    ) -> Word | None:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before getting due words")

        now = datetime.now(timezone.utc)
        word = self._repository.get_due_word_in_active_parts(
            user.user_id, now, exclude_word_id
        )
        if word is not None:
            return word
        return self._repository.get_due_word_in_active_parts(
            user.user_id, now + _DUE_LOOKAHEAD, exclude_word_id
        )

    def count_due(self, user: User) -> int:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before counting due words")
        return self._repository.count_due_words_in_active_parts(
            user.user_id, datetime.now(timezone.utc)
        )

    def count_study_due(self, user: User) -> int:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before counting due words")
        return self._repository.count_due_words_in_active_parts(
            user.user_id, datetime.now(timezone.utc) + _DUE_LOOKAHEAD
        )

    @staticmethod
    def get_projected_retrievability(word: Word) -> float:
        if word.status in {Status.KNOWN, Status.SUSPENDED}:
            return 1.0
        if word.status is Status.NEW:
            return 0.0
        now = datetime.now(timezone.utc)
        card = WordService._fsrs_card(word, now)
        return _SCHEDULER.get_card_retrievability(
            card, current_datetime=now + _READABILITY_HORIZON
        )

    def record_response(
        self,
        user: User,
        word: Word,
        response: Response,
        duration_ms: int | None = None,
    ) -> None:
        self._require_owned_word(user, word, "recording a response")
        if word.status not in _FSRS_STATES:
            raise ValueError("Known or suspended words cannot be reviewed")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("Review duration cannot be negative")

        reviewed_at = datetime.now(timezone.utc)
        status_before = word.status
        card = self._fsrs_card(word, reviewed_at)
        card, _ = _SCHEDULER.review_card(
            card,
            _RATINGS[response],
            review_datetime=reviewed_at,
            review_duration=duration_ms,
        )
        word.status = _WORD_STATUSES[card.state]
        word.step = card.step
        word.stability = card.stability or 0.0
        word.difficulty = card.difficulty or 0.0
        word.due = card.due
        word.last_reviewed = card.last_review
        self._repository.record_word_review(
            word,
            WordReview(
                None,
                word.word_id,
                response,
                status_before,
                reviewed_at,
                duration_ms,
            ),
        )

    def mark_known(self, user: User, word: Word) -> None:
        self._require_owned_word(user, word, "marking it known")
        word.status = Status.KNOWN
        word.step = None
        word.due = None
        self._repository.update_word_study(word)

    def _require_owned_word(self, user: User, word: Word, action: str) -> None:
        if (
            user.user_id is None
            or word.word_id is None
            or self._repository.get_user_word(user.user_id, word.word_id) is None
        ):
            raise ValueError(f"Word must belong to the user before {action}")

    @staticmethod
    def _fsrs_card(word: Word, now: datetime) -> Card:
        return Card(
            card_id=word.word_id,
            state=_FSRS_STATES[word.status],
            step=0 if word.status is Status.NEW else word.step,
            stability=word.stability if word.stability > 0 else None,
            difficulty=word.difficulty if word.difficulty > 0 else None,
            due=word.due or now,
            last_review=word.last_reviewed,
        )
