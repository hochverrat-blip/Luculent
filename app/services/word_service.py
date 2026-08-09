from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler, State

from app.domain import Response, Status, User, Word, WordReview
from app.services.base_service import Service


_SCHEDULER = Scheduler()

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

    def get_due(self, user: User) -> list[Word]:
        if user.user_id is None or self._repository.get_user(user.user_id) is None:
            raise ValueError("User must be saved before getting due words")

        now = datetime.now(timezone.utc)
        return self._repository.list_due_words_in_active_parts(
            user.user_id, now
        )

    def record_response(
        self,
        word: Word,
        response: Response,
        duration_ms: int | None = None,
    ) -> None:
        if word.word_id is None or self._repository.get_word(word.word_id) is None:
            raise ValueError("Word must be saved before recording a response")
        if word.status not in _FSRS_STATES:
            raise ValueError("Known or suspended words cannot be reviewed")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("Review duration cannot be negative")

        reviewed_at = datetime.now(timezone.utc)
        status_before = word.status
        card = Card(
            card_id=word.word_id,
            state=_FSRS_STATES[word.status],
            step=0 if word.status is Status.NEW else word.step,
            stability=word.stability if word.stability > 0 else None,
            difficulty=word.difficulty if word.difficulty > 0 else None,
            due=word.due or reviewed_at,
            last_review=word.last_reviewed,
        )
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

    def mark_known(self, word: Word) -> None:
        if word.word_id is None or self._repository.get_word(word.word_id) is None:
            raise ValueError("Word must be saved before marking it known")
        word.status = Status.KNOWN
        word.step = None
        word.due = None
        self._repository.update_word_study(word)
