from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path

from app.domain.document import DocPart, Document
from app.domain.enums import (
    Language,
    MeaningFrequency,
    MeaningLabel,
    POS,
    Response,
    Status,
)
from app.domain.user import User
from app.domain.word import DocPartWord, Word, WordMeaning, WordReview
from app.repositories.base import Repository


class SQLiteRepository(Repository):

    def __init__(self, database_path: str | Path = "luculent.db"):
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created TEXT NOT NULL,
                native_language TEXT NOT NULL DEFAULT 'ENGLISH'
            );

            CREATE TABLE IF NOT EXISTS documents (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                language TEXT NOT NULL,
                imported TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS doc_parts (
                doc_part_id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                position INTEGER NOT NULL,
                readability REAL NOT NULL DEFAULT 0.0,
                active INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (document_id)
                    REFERENCES documents(document_id) ON DELETE CASCADE,
                UNIQUE (document_id, position)
            );

            CREATE TABLE IF NOT EXISTS lexicon_entries (
                lexicon_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lemma TEXT NOT NULL,
                language TEXT NOT NULL,
                pos TEXT NOT NULL,
                UNIQUE (lemma, language, pos)
            );

            CREATE TABLE IF NOT EXISTS lexicon_metadata (
                source TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                checksum TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS words (
                word_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lexicon_entry_id INTEGER NOT NULL,
                due TEXT,
                difficulty REAL NOT NULL DEFAULT 0.0,
                stability REAL NOT NULL DEFAULT 0.0,
                image_path TEXT,
                status TEXT NOT NULL,
                last_reviewed TEXT,
                step INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (lexicon_entry_id)
                    REFERENCES lexicon_entries(lexicon_entry_id),
                UNIQUE (user_id, lexicon_entry_id)
            );

            CREATE TABLE IF NOT EXISTS word_meanings (
                meaning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lexicon_entry_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'USER',
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss TEXT NOT NULL,
                frequency TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                FOREIGN KEY (lexicon_entry_id)
                    REFERENCES lexicon_entries(lexicon_entry_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS word_reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id INTEGER NOT NULL,
                response TEXT NOT NULL,
                status_before TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                duration_ms INTEGER,
                FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS word_meaning_labels (
                meaning_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY (meaning_id, label),
                FOREIGN KEY (meaning_id)
                    REFERENCES word_meanings(meaning_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS doc_part_words (
                word_id INTEGER NOT NULL,
                doc_part_id INTEGER NOT NULL,
                occurrences INTEGER NOT NULL CHECK (occurrences >= 0),
                PRIMARY KEY (word_id, doc_part_id),
                FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE,
                FOREIGN KEY (doc_part_id)
                    REFERENCES doc_parts(doc_part_id) ON DELETE CASCADE
            );
            """
        )
        self._connection.commit()
        self._initialized = True

    def save_user(self, user: User) -> None:
        if user.user_id is None:
            user._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO users (name, created, native_language)
                    VALUES (?, ?, ?)
                    """,
                    (
                        user.name,
                        user.created.isoformat(),
                        user.native_language.name,
                    ),
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO users (user_id, name, created, native_language)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                created = excluded.created,
                native_language = excluded.native_language
            """,
            (
                user.user_id,
                user.name,
                user.created.isoformat(),
                user.native_language.name,
            ),
        )
        self._connection.commit()

    def get_user(self, user_id: int) -> User | None:
        row = self._connection.execute(
            """
            SELECT user_id, name, created, native_language
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        return User(
            user_id=row["user_id"],
            name=row["name"],
            created=date.fromisoformat(row["created"]),
            native_language=Language[row["native_language"]],
        )

    def get_user_by_name(self, name: str) -> User | None:
        row = self._connection.execute(
            "SELECT user_id FROM users WHERE name = ?",
            (name,),
        ).fetchone()
        return None if row is None else self.get_user(row["user_id"])

    def delete_user(self, user_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM users WHERE user_id = ?",
            (user_id,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def save_document(self, user_id: int, document: Document) -> None:
        self._save_document(user_id, document, commit=True)

    def save_document_with_parts(self, user_id: int, document: Document) -> None:
        document_was_new = document.document_id is None
        new_parts = [part for part in document.doc_parts if part.doc_part_id is None]
        try:
            self._save_document(user_id, document, commit=False)
            for doc_part in document.doc_parts:
                self._save_doc_part(document.document_id, doc_part, commit=False)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            if document_was_new:
                document._assign_id(None)
            for doc_part in new_parts:
                doc_part._assign_id(None)
            raise

    def save_document_import(
        self,
        user_id: int,
        document: Document,
        associations: list[DocPartWord],
    ) -> None:
        document_was_new = document.document_id is None
        new_parts = [part for part in document.doc_parts if part.doc_part_id is None]
        new_words = list(
            {
                id(association.word): association.word
                for association in associations
                if association.word.word_id is None
            }.values()
        )
        try:
            self._save_document(user_id, document, commit=False)
            for doc_part in document.doc_parts:
                self._save_doc_part(document.document_id, doc_part, commit=False)
            for word in new_words:
                self._save_word(user_id, word, commit=False)
            for association in associations:
                self._save_doc_part_word(association, commit=False)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            if document_was_new:
                document._assign_id(None)
            for doc_part in new_parts:
                doc_part._assign_id(None)
            for word in new_words:
                word._assign_id(None)
            raise

    def _save_document(
        self, user_id: int, document: Document, *, commit: bool
    ) -> None:
        if document.document_id is None:
            document._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO documents (user_id, title, text, language, imported)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        document.title,
                        document.text,
                        document.language.name,
                        document.imported.isoformat(),
                    ),
                    commit=commit,
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO documents (
                document_id, user_id, title, text, language, imported
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                user_id = excluded.user_id,
                title = excluded.title,
                text = excluded.text,
                language = excluded.language,
                imported = excluded.imported
            """,
            (
                document.document_id,
                user_id,
                document.title,
                document.text,
                document.language.name,
                document.imported.isoformat(),
            ),
        )
        if commit:
            self._connection.commit()

    def get_document(self, document_id: int) -> Document | None:
        row = self._connection.execute(
            """
            SELECT document_id, title, text, language, imported
            FROM documents
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        return self._document_from_row(row)

    def list_documents(self, user_id: int) -> list[Document]:
        rows = self._connection.execute(
            """
            SELECT document_id, title, text, language, imported
            FROM documents
            WHERE user_id = ?
            ORDER BY imported, document_id
            """,
            (user_id,),
        ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def save_doc_part(self, document_id: int, doc_part: DocPart) -> None:
        self._save_doc_part(document_id, doc_part, commit=True)

    def _save_doc_part(
        self, document_id: int, doc_part: DocPart, *, commit: bool
    ) -> None:
        if doc_part.doc_part_id is None:
            doc_part._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO doc_parts (
                        document_id, text, position, readability, active
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        doc_part.text,
                        doc_part.position,
                        doc_part.readability,
                        int(doc_part.active),
                    ),
                    commit=commit,
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO doc_parts (
                doc_part_id, document_id, text, position, readability, active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_part_id) DO UPDATE SET
                document_id = excluded.document_id,
                text = excluded.text,
                position = excluded.position,
                readability = excluded.readability,
                active = excluded.active
            """,
            (
                doc_part.doc_part_id,
                document_id,
                doc_part.text,
                doc_part.position,
                doc_part.readability,
                int(doc_part.active),
            ),
        )
        if commit:
            self._connection.commit()

    def list_doc_parts(self, document_id: int) -> list[DocPart]:
        rows = self._connection.execute(
            """
            SELECT doc_part_id, text, position, readability, active
            FROM doc_parts
            WHERE document_id = ?
            ORDER BY position, doc_part_id
            """,
            (document_id,),
        ).fetchall()
        return [self._doc_part_from_row(row) for row in rows]

    def activate_doc_part(self, user_id: int, doc_part_id: int) -> None:
        try:
            owned = self._connection.execute(
                """
                SELECT 1
                FROM doc_parts AS dp
                INNER JOIN documents AS d ON d.document_id = dp.document_id
                WHERE dp.doc_part_id = ? AND d.user_id = ?
                """,
                (doc_part_id, user_id),
            ).fetchone()
            if owned is None:
                raise ValueError("Document part must belong to the user")
            self._connection.execute(
                """
                UPDATE doc_parts
                SET active = 0
                WHERE document_id IN (
                    SELECT document_id FROM documents WHERE user_id = ?
                )
                """,
                (user_id,),
            )
            self._connection.execute(
                "UPDATE doc_parts SET active = 1 WHERE doc_part_id = ?",
                (doc_part_id,),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def save_word(self, user_id: int, word: Word) -> None:
        self._save_word(user_id, word, commit=True)

    def _save_word(self, user_id: int, word: Word, *, commit: bool) -> None:
        lexicon_entry_id = self._ensure_lexicon_entry(word)
        if word.word_id is None:
            word._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO words (
                        user_id, lexicon_entry_id, due, difficulty, stability,
                        image_path, status, last_reviewed, step
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        lexicon_entry_id,
                        self._datetime_to_text(word.due),
                        word.difficulty,
                        word.stability,
                        word.image_path,
                        word.status.name,
                        self._datetime_to_text(word.last_reviewed),
                        word.step,
                    ),
                    commit=commit,
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO words (
                word_id, user_id, lexicon_entry_id, due, difficulty,
                stability, image_path, status, last_reviewed, step
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word_id) DO UPDATE SET
                user_id = excluded.user_id,
                lexicon_entry_id = excluded.lexicon_entry_id,
                due = excluded.due,
                difficulty = excluded.difficulty,
                stability = excluded.stability,
                image_path = excluded.image_path,
                status = excluded.status,
                last_reviewed = excluded.last_reviewed,
                step = excluded.step
            """,
            (
                word.word_id,
                user_id,
                lexicon_entry_id,
                self._datetime_to_text(word.due),
                word.difficulty,
                word.stability,
                word.image_path,
                word.status.name,
                self._datetime_to_text(word.last_reviewed),
                word.step,
            ),
        )
        if commit:
            self._connection.commit()

    def get_word(self, word_id: int) -> Word | None:
        row = self._connection.execute(
            """
            SELECT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE w.word_id = ?
            """,
            (word_id,),
        ).fetchone()
        if row is None:
            return None
        return self._word_from_row(row)

    def list_words(self, user_id: int) -> list[Word]:
        rows = self._connection.execute(
            """
            SELECT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE w.user_id = ?
            ORDER BY w.word_id
            """,
            (user_id,),
        ).fetchall()
        return [self._word_from_row(row) for row in rows]

    def list_words_by_lemmas(
        self, user_id: int, language: Language, lemmas: set[str]
    ) -> list[Word]:
        rows: list[sqlite3.Row] = []
        ordered_lemmas = sorted(lemmas)
        for start in range(0, len(ordered_lemmas), 500):
            chunk = ordered_lemmas[start : start + 500]
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._connection.execute(
                    f"""
                    SELECT w.*, le.lemma, le.language, le.pos
                    FROM words AS w
                    INNER JOIN lexicon_entries AS le
                        ON le.lexicon_entry_id = w.lexicon_entry_id
                    WHERE w.user_id = ?
                      AND le.language = ?
                      AND le.lemma IN ({placeholders})
                    """,
                    (user_id, language.name, *chunk),
                ).fetchall()
            )
        rows.sort(key=lambda row: row["word_id"])
        return [self._word_from_row(row) for row in rows]

    def update_word_study(self, word: Word) -> None:
        if word.word_id is None:
            raise ValueError("Word must be saved before recording a response")
        try:
            self._update_word_study(word)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def record_word_review(self, word: Word, review: WordReview) -> None:
        try:
            self._update_word_study(word)
            review._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO word_reviews (
                        word_id, response, status_before, reviewed_at, duration_ms
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        review.word_id,
                        review.response.name,
                        review.status_before.name,
                        self._datetime_to_text(review.reviewed_at),
                        review.duration_ms,
                    ),
                    commit=False,
                )
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            review._assign_id(None)
            raise

    def list_word_reviews(self, word_id: int) -> list[WordReview]:
        rows = self._connection.execute(
            """
            SELECT review_id, word_id, response, status_before, reviewed_at,
                   duration_ms
            FROM word_reviews
            WHERE word_id = ?
            ORDER BY reviewed_at, review_id
            """,
            (word_id,),
        ).fetchall()
        return [
            WordReview(
                row["review_id"],
                row["word_id"],
                Response[row["response"]],
                Status[row["status_before"]],
                self._text_to_datetime(row["reviewed_at"]),
                row["duration_ms"],
            )
            for row in rows
        ]

    def _update_word_study(self, word: Word) -> None:
        cursor = self._connection.execute(
            """
            UPDATE words
            SET due = ?, difficulty = ?, stability = ?, status = ?,
                last_reviewed = ?, step = ?
            WHERE word_id = ?
            """,
            (
                self._datetime_to_text(word.due),
                word.difficulty,
                word.stability,
                word.status.name,
                self._datetime_to_text(word.last_reviewed),
                word.step,
                word.word_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError("Word must be saved before recording a response")

    def save_word_meaning(self, word_id: int, meaning: WordMeaning) -> None:
        self._save_word_meaning(word_id, meaning, commit=True)

    def _save_word_meaning(
        self, word_id: int, meaning: WordMeaning, *, commit: bool
    ) -> None:
        entry = self._connection.execute(
            "SELECT lexicon_entry_id FROM words WHERE word_id = ?",
            (word_id,),
        ).fetchone()
        if entry is None:
            raise ValueError("Word must be saved before its meaning")
        lexicon_entry_id = entry["lexicon_entry_id"]
        if meaning.meaning_id is None:
            meaning._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO word_meanings (
                        lexicon_entry_id, source, korean_definition,
                        english_definition, gloss, frequency, display_order
                    )
                    VALUES (?, 'USER', ?, ?, ?, ?, ?)
                    """,
                    (
                        lexicon_entry_id,
                        meaning.korean_definition,
                        meaning.english_definition,
                        meaning.gloss,
                        meaning.frequency.name,
                        meaning.display_order,
                    ),
                    commit=False,
                )
            )
        else:
            self._connection.execute(
                """
                INSERT INTO word_meanings (
                    meaning_id, lexicon_entry_id, source, korean_definition,
                    english_definition, gloss, frequency, display_order
                )
                VALUES (?, ?, 'USER', ?, ?, ?, ?, ?)
                ON CONFLICT(meaning_id) DO UPDATE SET
                    lexicon_entry_id = excluded.lexicon_entry_id,
                    korean_definition = excluded.korean_definition,
                    english_definition = excluded.english_definition,
                    gloss = excluded.gloss,
                    frequency = excluded.frequency,
                    display_order = excluded.display_order
                """,
                (
                    meaning.meaning_id,
                    lexicon_entry_id,
                    meaning.korean_definition,
                    meaning.english_definition,
                    meaning.gloss,
                    meaning.frequency.name,
                    meaning.display_order,
                ),
            )
        self._connection.execute(
            "DELETE FROM word_meaning_labels WHERE meaning_id = ?",
            (meaning.meaning_id,),
        )
        self._connection.executemany(
            "INSERT INTO word_meaning_labels (meaning_id, label) VALUES (?, ?)",
            ((meaning.meaning_id, label.name) for label in meaning.labels),
        )
        if commit:
            self._connection.commit()

    def list_word_meanings(self, word_id: int) -> list[WordMeaning]:
        rows = self._connection.execute(
            """
            SELECT *
            FROM word_meanings
            WHERE lexicon_entry_id = (
                SELECT lexicon_entry_id FROM words WHERE word_id = ?
            )
            ORDER BY display_order, meaning_id
            """,
            (word_id,),
        ).fetchall()
        meanings = [self._word_meaning_from_row(row) for row in rows]
        for meaning in meanings:
            labels = self._connection.execute(
                """
                SELECT label
                FROM word_meaning_labels
                WHERE meaning_id = ?
                ORDER BY label
                """,
                (meaning.meaning_id,),
            ).fetchall()
            meaning.labels.update(MeaningLabel[row["label"]] for row in labels)
        return meanings

    def list_due_words_in_active_parts(
        self, user_id: int, due_at: datetime
    ) -> list[Word]:
        rows = self._connection.execute(
            """
            SELECT DISTINCT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            INNER JOIN doc_part_words AS dpw ON dpw.word_id = w.word_id
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE w.user_id = ?
              AND d.user_id = ?
              AND w.status IN (?, ?, ?, ?)
              AND (w.due IS NULL OR w.due <= ?)
              AND dp.active = 1
            ORDER BY w.due IS NOT NULL, w.due, w.word_id
            """,
            (
                user_id,
                user_id,
                Status.NEW.name,
                Status.LEARNING.name,
                Status.REVIEW.name,
                Status.RELEARNING.name,
                self._datetime_to_text(due_at),
            ),
        ).fetchall()
        return [self._word_from_row(row) for row in rows]

    def save_doc_part_word(self, association: DocPartWord) -> None:
        self._save_doc_part_word(association, commit=True)

    def _save_doc_part_word(
        self, association: DocPartWord, *, commit: bool
    ) -> None:
        if association.word.word_id is None or association.doc_part.doc_part_id is None:
            raise ValueError("Word and document part must be saved first")
        ownership = self._connection.execute(
            """
            SELECT 1
            FROM words AS w
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = ?
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE w.word_id = ?
              AND w.user_id = d.user_id
            """,
            (association.doc_part.doc_part_id, association.word.word_id),
        ).fetchone()
        if ownership is None:
            raise ValueError("Word and document part must belong to the same user")
        self._connection.execute(
            """
            INSERT INTO doc_part_words (word_id, doc_part_id, occurrences)
            VALUES (?, ?, ?)
            ON CONFLICT(word_id, doc_part_id) DO UPDATE SET
                occurrences = excluded.occurrences
            """,
            (
                association.word.word_id,
                association.doc_part.doc_part_id,
                association.occurrences,
            ),
        )
        if commit:
            self._connection.commit()

    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        rows = self._connection.execute(
            """
            SELECT dpw.occurrences, dp.doc_part_id, dp.text, dp.position,
                   dp.readability, dp.active, w.*,
                   le.lemma, le.language, le.pos
            FROM doc_part_words AS dpw
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN words AS w ON w.word_id = dpw.word_id
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE dpw.doc_part_id = ?
            ORDER BY w.word_id
            """,
            (doc_part_id,),
        ).fetchall()
        return [
            DocPartWord(
                word=self._word_from_row(row),
                doc_part=self._doc_part_from_row(row),
                occurrences=row["occurrences"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()

    def get_lexicon_version(self, source: str) -> str | None:
        row = self._connection.execute(
            "SELECT version FROM lexicon_metadata WHERE source = ?",
            (source,),
        ).fetchone()
        return None if row is None else row["version"]

    def install_lexicon(
        self,
        source: str,
        version: str,
        checksum: str,
        meanings: Iterable[tuple[str, Language, POS, WordMeaning]],
    ) -> None:
        try:
            meaning_ids = self._connection.execute(
                "SELECT meaning_id FROM word_meanings WHERE source = ?",
                (source,),
            ).fetchall()
            self._connection.executemany(
                "DELETE FROM word_meaning_labels WHERE meaning_id = ?",
                ((row["meaning_id"],) for row in meaning_ids),
            )
            self._connection.execute(
                "DELETE FROM word_meanings WHERE source = ?", (source,)
            )
            for lemma, language, pos, meaning in meanings:
                entry_id = self._ensure_lexicon_entry_values(lemma, language, pos)
                meaning._assign_id(
                    self._execute_insert(
                        """
                        INSERT INTO word_meanings (
                            lexicon_entry_id, source, korean_definition,
                            english_definition, gloss, frequency, display_order
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry_id,
                            source,
                            meaning.korean_definition,
                            meaning.english_definition,
                            meaning.gloss,
                            meaning.frequency.name,
                            meaning.display_order,
                        ),
                        commit=False,
                    )
                )
                self._connection.executemany(
                    "INSERT INTO word_meaning_labels (meaning_id, label) VALUES (?, ?)",
                    ((meaning.meaning_id, label.name) for label in meaning.labels),
                )
            self._connection.execute(
                """
                INSERT INTO lexicon_metadata (source, version, checksum)
                VALUES (?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    version = excluded.version,
                    checksum = excluded.checksum
                """,
                (source, version, checksum),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _ensure_lexicon_entry(self, word: Word) -> int:
        return self._ensure_lexicon_entry_values(
            word.lemma, word.language, word.pos
        )

    def _ensure_lexicon_entry_values(
        self, lemma: str, language: Language, pos: POS
    ) -> int:
        self._connection.execute(
            """
            INSERT INTO lexicon_entries (lemma, language, pos)
            VALUES (?, ?, ?)
            ON CONFLICT(lemma, language, pos) DO NOTHING
            """,
            (lemma, language.name, pos.name),
        )
        row = self._connection.execute(
            """
            SELECT lexicon_entry_id
            FROM lexicon_entries
            WHERE lemma = ? AND language = ? AND pos = ?
            """,
            (lemma, language.name, pos.name),
        ).fetchone()
        return row["lexicon_entry_id"]

    def _execute_insert(
        self,
        sql: str,
        parameters: tuple[object, ...],
        *,
        commit: bool = True,
    ) -> int:
        cursor = self._connection.execute(sql, parameters)
        if commit:
            self._connection.commit()
        return cursor.lastrowid

    def _document_from_row(self, row: sqlite3.Row) -> Document:
        document = Document(
            document_id=row["document_id"],
            title=row["title"],
            text=row["text"],
            language=Language[row["language"]],
            imported=date.fromisoformat(row["imported"]),
        )
        document.doc_parts.extend(self.list_doc_parts(document.document_id))
        return document

    @staticmethod
    def _doc_part_from_row(row: sqlite3.Row) -> DocPart:
        return DocPart(
            doc_part_id=row["doc_part_id"],
            text=row["text"],
            position=row["position"],
            readability=row["readability"],
            active=bool(row["active"]),
        )

    def _word_from_row(self, row: sqlite3.Row) -> Word:
        word = Word(
            word_id=row["word_id"],
            lemma=row["lemma"],
            language=Language[row["language"]],
            pos=POS[row["pos"]],
        )
        word.due = SQLiteRepository._text_to_datetime(row["due"])
        word.difficulty = row["difficulty"]
        word.stability = row["stability"]
        word.image_path = row["image_path"]
        word.status = Status[row["status"]]
        word.last_reviewed = SQLiteRepository._text_to_datetime(
            row["last_reviewed"]
        )
        word.step = row["step"]
        word.meanings.extend(self.list_word_meanings(word.word_id))
        return word

    @staticmethod
    def _word_meaning_from_row(row: sqlite3.Row) -> WordMeaning:
        return WordMeaning(
            meaning_id=row["meaning_id"],
            korean_definition=row["korean_definition"],
            english_definition=row["english_definition"],
            gloss=row["gloss"],
            frequency=MeaningFrequency[row["frequency"]],
            display_order=row["display_order"],
        )

    @staticmethod
    def _datetime_to_text(value: datetime | None) -> str | None:
        return value.astimezone(timezone.utc).isoformat() if value is not None else None

    @staticmethod
    def _text_to_datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None
