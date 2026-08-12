from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.domain.document import DocPart, Document
from app.domain.enums import (
    Language,
    POS,
    Response,
    Status,
)
from app.domain.user import User
from app.domain.word import (
    DocPartWord,
    UserWordMeaning,
    Word,
    WordMeaning,
    WordReview,
)
from app.repositories.base import Repository
from app.settings import Settings


class MySQLRepository(Repository):

    def __init__(
        self,
        settings: Settings,
        *,
        connect: Callable[..., Any] | None = None,
    ):
        if connect is None:
            try:
                from mysql.connector import connect as mysql_connect
            except ImportError as error:
                raise RuntimeError(
                    "MySQL support requires mysql-connector-python"
                ) from error
            connect = mysql_connect

        self._connection = connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            database=settings.mysql_database,
            user=settings.mysql_user,
            password=settings.mysql_password,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        statements = (
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                name_key VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
                    NOT NULL UNIQUE,
                created DATE NOT NULL,
                native_language VARCHAR(50) NOT NULL DEFAULT 'ENGLISH'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(500) NOT NULL,
                text LONGTEXT NOT NULL,
                language VARCHAR(50) NOT NULL,
                imported DATE NOT NULL,
                CONSTRAINT fk_documents_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS doc_parts (
                doc_part_id INT AUTO_INCREMENT PRIMARY KEY,
                document_id INT NOT NULL,
                text LONGTEXT NOT NULL,
                position INT NOT NULL,
                readability DOUBLE NOT NULL DEFAULT 0.0,
                active BOOLEAN NOT NULL DEFAULT FALSE,
                CONSTRAINT fk_doc_parts_document
                    FOREIGN KEY (document_id) REFERENCES documents(document_id)
                    ON DELETE CASCADE,
                CONSTRAINT uq_doc_parts_position UNIQUE (document_id, position)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS lexicon_entries (
                lexicon_entry_id INT AUTO_INCREMENT PRIMARY KEY,
                lemma VARCHAR(500) NOT NULL,
                language VARCHAR(50) NOT NULL,
                pos VARCHAR(50) NOT NULL,
                CONSTRAINT uq_lexicon_entry UNIQUE (lemma, language, pos)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS lexicon_metadata (
                source VARCHAR(255) PRIMARY KEY,
                version VARCHAR(100) NOT NULL,
                checksum VARCHAR(100) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS words (
                word_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                lexicon_entry_id INT NOT NULL,
                due DATETIME(6) NULL,
                difficulty DOUBLE NOT NULL DEFAULT 0.0,
                stability DOUBLE NOT NULL DEFAULT 0.0,
                image_path VARCHAR(1000) NULL,
                status VARCHAR(50) NOT NULL,
                last_reviewed DATETIME(6) NULL,
                step INT NULL,
                CONSTRAINT fk_words_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_words_lexicon_entry
                    FOREIGN KEY (lexicon_entry_id)
                    REFERENCES lexicon_entries(lexicon_entry_id),
                CONSTRAINT uq_words_user_entry
                    UNIQUE (user_id, lexicon_entry_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS word_meanings (
                meaning_id INT AUTO_INCREMENT PRIMARY KEY,
                lexicon_entry_id INT NOT NULL,
                source VARCHAR(255) NOT NULL DEFAULT 'USER',
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss VARCHAR(500) NOT NULL,
                display_order INT NOT NULL,
                CONSTRAINT fk_word_meanings_entry
                    FOREIGN KEY (lexicon_entry_id)
                    REFERENCES lexicon_entries(lexicon_entry_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS word_reviews (
                review_id INT AUTO_INCREMENT PRIMARY KEY,
                word_id INT NOT NULL,
                response VARCHAR(50) NOT NULL,
                status_before VARCHAR(50) NOT NULL,
                reviewed_at DATETIME(6) NOT NULL,
                duration_ms INT NULL,
                CONSTRAINT fk_word_reviews_word
                    FOREIGN KEY (word_id) REFERENCES words(word_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS user_word_meanings (
                user_meaning_id INT AUTO_INCREMENT PRIMARY KEY,
                word_id INT NOT NULL,
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss VARCHAR(500) NOT NULL,
                display_order INT NOT NULL,
                CONSTRAINT fk_user_word_meanings_word
                    FOREIGN KEY (word_id) REFERENCES words(word_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS doc_part_words (
                word_id INT NOT NULL,
                doc_part_id INT NOT NULL,
                occurrences INT NOT NULL,
                PRIMARY KEY (word_id, doc_part_id),
                CONSTRAINT chk_occurrences_nonnegative CHECK (occurrences >= 0),
                CONSTRAINT fk_doc_part_words_word
                    FOREIGN KEY (word_id) REFERENCES words(word_id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_doc_part_words_part
                    FOREIGN KEY (doc_part_id) REFERENCES doc_parts(doc_part_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        )
        cursor = self._connection.cursor()
        try:
            for statement in statements:
                cursor.execute(statement)
            self._connection.commit()
            self._initialized = True
        finally:
            cursor.close()

    def save_user(self, user: User) -> None:
        if user.user_id is None:
            user._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO users (name, name_key, created, native_language)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user.name,
                        user.name.casefold(),
                        user.created,
                        user.native_language.name,
                    ),
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO users (user_id, name, name_key, created, native_language)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                name_key = VALUES(name_key),
                created = VALUES(created),
                native_language = VALUES(native_language)
            """,
            (
                user.user_id,
                user.name,
                user.name.casefold(),
                user.created,
                user.native_language.name,
            ),
        )

    def get_user(self, user_id: int) -> User | None:
        row = self._fetch_one(
            """
            SELECT user_id, name, created, native_language
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        if row is None:
            return None
        return User(
            user_id=row["user_id"],
            name=row["name"],
            created=self._as_date(row["created"]),
            native_language=Language[row["native_language"]],
        )

    def get_user_by_name(self, name: str) -> User | None:
        row = self._fetch_one(
            "SELECT user_id FROM users WHERE name_key = %s",
            (name.casefold(),),
        )
        return None if row is None else self.get_user(row["user_id"])

    def list_users(self) -> list[User]:
        rows = self._fetch_all(
            "SELECT user_id FROM users ORDER BY name, user_id", ()
        )
        return [self.get_user(row["user_id"]) for row in rows]

    def delete_user(self, user_id: int) -> bool:
        return self._execute_delete(
            "DELETE FROM users WHERE user_id = %s",
            (user_id,),
        )

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
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        document.title,
                        document.text,
                        document.language.name,
                        document.imported,
                    ),
                    commit=commit,
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO documents (
                document_id, user_id, title, text, language, imported
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                title = VALUES(title),
                text = VALUES(text),
                language = VALUES(language),
                imported = VALUES(imported)
            """,
            (
                document.document_id,
                user_id,
                document.title,
                document.text,
                document.language.name,
                document.imported,
            ),
            commit=commit,
        )

    def get_document(self, document_id: int) -> Document | None:
        row = self._fetch_one(
            """
            SELECT document_id, title, text, language, imported
            FROM documents
            WHERE document_id = %s
            """,
            (document_id,),
        )
        return None if row is None else self._document_from_row(row)

    def list_documents(self, user_id: int) -> list[Document]:
        rows = self._fetch_all(
            """
            SELECT document_id, title, text, language, imported
            FROM documents
            WHERE user_id = %s
            ORDER BY imported, document_id
            """,
            (user_id,),
        )
        return [self._document_from_row(row) for row in rows]

    def delete_document(self, user_id: int, document_id: int) -> bool:
        return self._execute_delete(
            "DELETE FROM documents WHERE document_id = %s AND user_id = %s",
            (document_id, user_id),
        )

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
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        doc_part.text,
                        doc_part.position,
                        doc_part.readability,
                        doc_part.active,
                    ),
                    commit=commit,
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO doc_parts (
                doc_part_id, document_id, text, position, readability, active
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                document_id = VALUES(document_id),
                text = VALUES(text),
                position = VALUES(position),
                readability = VALUES(readability),
                active = VALUES(active)
            """,
            (
                doc_part.doc_part_id,
                document_id,
                doc_part.text,
                doc_part.position,
                doc_part.readability,
                doc_part.active,
            ),
            commit=commit,
        )

    def list_doc_parts(self, document_id: int) -> list[DocPart]:
        rows = self._fetch_all(
            """
            SELECT doc_part_id, text, position, readability, active
            FROM doc_parts
            WHERE document_id = %s
            ORDER BY position, doc_part_id
            """,
            (document_id,),
        )
        return [self._doc_part_from_row(row) for row in rows]

    def get_users_doc_part(self, user_id: int, doc_part_id: int) -> DocPart | None:
        row = self._fetch_one(
            """
            SELECT dp.doc_part_id, dp.text, dp.position, dp.readability, dp.active
            FROM doc_parts AS dp
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE d.user_id = %s AND dp.doc_part_id = %s
            """,
            (user_id, doc_part_id),
        )
        return None if row is None else self._doc_part_from_row(row)

    def get_users_doc_part_language(
        self, user_id: int, doc_part_id: int
    ) -> Language | None:
        row = self._fetch_one(
            """
            SELECT d.language
            FROM doc_parts AS dp
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE d.user_id = %s AND dp.doc_part_id = %s
            """,
            (user_id, doc_part_id),
        )
        return None if row is None else Language[row["language"]]

    def activate_doc_part(self, user_id: int, doc_part_id: int) -> None:
        cursor = self._connection.cursor()
        try:
            owned = self._fetch_one(
                """
                SELECT 1 AS owned
                FROM doc_parts AS dp
                INNER JOIN documents AS d ON d.document_id = dp.document_id
                WHERE dp.doc_part_id = %s AND d.user_id = %s
                """,
                (doc_part_id, user_id),
            )
            if owned is None:
                raise ValueError("Document part must belong to the user")
            cursor.execute(
                """
                UPDATE doc_parts AS dp
                INNER JOIN documents AS d ON d.document_id = dp.document_id
                SET dp.active = FALSE
                WHERE d.user_id = %s
                """,
                (user_id,),
            )
            cursor.execute(
                "UPDATE doc_parts SET active = TRUE WHERE doc_part_id = %s",
                (doc_part_id,),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        lexicon_entry_id,
                        self._datetime_to_mysql(word.due),
                        word.difficulty,
                        word.stability,
                        word.image_path,
                        word.status.name,
                        self._datetime_to_mysql(word.last_reviewed),
                        word.step,
                    ),
                    commit=commit,
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO words (
                word_id, user_id, lexicon_entry_id, due, difficulty,
                stability, image_path, status, last_reviewed, step
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                lexicon_entry_id = VALUES(lexicon_entry_id),
                due = VALUES(due),
                difficulty = VALUES(difficulty),
                stability = VALUES(stability),
                image_path = VALUES(image_path),
                status = VALUES(status),
                last_reviewed = VALUES(last_reviewed),
                step = VALUES(step)
            """,
            (
                word.word_id,
                user_id,
                lexicon_entry_id,
                self._datetime_to_mysql(word.due),
                word.difficulty,
                word.stability,
                word.image_path,
                word.status.name,
                self._datetime_to_mysql(word.last_reviewed),
                word.step,
            ),
            commit=commit,
        )

    def get_word(self, word_id: int) -> Word | None:
        row = self._fetch_one(
            """
            SELECT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE w.word_id = %s
            """,
            (word_id,),
        )
        return None if row is None else self._word_from_row(row)

    def get_user_word(self, user_id: int, word_id: int) -> Word | None:
        row = self._fetch_one(
            """
            SELECT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE w.user_id = %s AND w.word_id = %s
            """,
            (user_id, word_id),
        )
        return None if row is None else self._word_from_row(row)

    def list_words(self, user_id: int) -> list[Word]:
        rows = self._fetch_all(
            """
            SELECT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE w.user_id = %s
            ORDER BY w.word_id
            """,
            (user_id,),
        )
        return [self._word_from_row(row) for row in rows]

    def list_words_by_lemmas(
        self, user_id: int, language: Language, lemmas: set[str]
    ) -> list[Word]:
        rows: list[dict[str, Any]] = []
        ordered_lemmas = sorted(lemmas)
        for start in range(0, len(ordered_lemmas), 500):
            chunk = ordered_lemmas[start : start + 500]
            placeholders = ", ".join("%s" for _ in chunk)
            rows.extend(
                self._fetch_all(
                    f"""
                    SELECT w.*, le.lemma, le.language, le.pos
                    FROM words AS w
                    INNER JOIN lexicon_entries AS le
                        ON le.lexicon_entry_id = w.lexicon_entry_id
                    WHERE w.user_id = %s
                      AND le.language = %s
                      AND le.lemma IN ({placeholders})
                    """,
                    (user_id, language.name, *chunk),
                )
            )
        rows.sort(key=lambda row: row["word_id"])
        return [self._word_study_from_row(row) for row in rows]

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
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        review.word_id,
                        review.response.name,
                        review.status_before.name,
                        self._datetime_to_mysql(review.reviewed_at),
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
        rows = self._fetch_all(
            """
            SELECT review_id, word_id, response, status_before, reviewed_at,
                   duration_ms
            FROM word_reviews
            WHERE word_id = %s
            ORDER BY reviewed_at, review_id
            """,
            (word_id,),
        )
        return [
            WordReview(
                row["review_id"],
                row["word_id"],
                Response[row["response"]],
                Status[row["status_before"]],
                self._mysql_to_datetime(row["reviewed_at"]),
                row["duration_ms"],
            )
            for row in rows
        ]

    def _update_word_study(self, word: Word) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """
                UPDATE words
                SET due = %s, difficulty = %s, stability = %s, status = %s,
                    last_reviewed = %s, step = %s
                WHERE word_id = %s
                """,
                (
                    self._datetime_to_mysql(word.due),
                    word.difficulty,
                    word.stability,
                    word.status.name,
                    self._datetime_to_mysql(word.last_reviewed),
                    word.step,
                    word.word_id,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "SELECT 1 FROM words WHERE word_id = %s",
                    (word.word_id,),
                )
                if cursor.fetchone() is None:
                    raise ValueError("Word must be saved before recording a response")
        finally:
            cursor.close()

    def save_word_meaning(self, word_id: int, meaning: WordMeaning) -> None:
        self._save_word_meaning(word_id, meaning, commit=True)

    def _save_word_meaning(
        self, word_id: int, meaning: WordMeaning, *, commit: bool
    ) -> None:
        entry = self._fetch_one(
            "SELECT lexicon_entry_id FROM words WHERE word_id = %s",
            (word_id,),
        )
        if entry is None:
            raise ValueError("Word must be saved before its meaning")
        lexicon_entry_id = entry["lexicon_entry_id"]
        if meaning.meaning_id is None:
            meaning._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO word_meanings (
                        lexicon_entry_id, source, korean_definition,
                        english_definition, gloss, display_order
                    )
                    VALUES (%s, 'USER', %s, %s, %s, %s)
                    """,
                    (
                        lexicon_entry_id,
                        meaning.korean_definition,
                        meaning.english_definition,
                        meaning.gloss,
                        meaning.display_order,
                    ),
                    commit=False,
                )
            )
        else:
            self._execute_write(
                """
                INSERT INTO word_meanings (
                    meaning_id, lexicon_entry_id, source, korean_definition,
                    english_definition, gloss, display_order
                )
                VALUES (%s, %s, 'USER', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    lexicon_entry_id = VALUES(lexicon_entry_id),
                    korean_definition = VALUES(korean_definition),
                    english_definition = VALUES(english_definition),
                    gloss = VALUES(gloss),
                    display_order = VALUES(display_order)
                """,
                (
                    meaning.meaning_id,
                    lexicon_entry_id,
                    meaning.korean_definition,
                    meaning.english_definition,
                    meaning.gloss,
                    meaning.display_order,
                ),
                commit=False,
            )
        if commit:
            self._connection.commit()

    def list_word_meanings(self, word_id: int) -> list[WordMeaning]:
        rows = self._fetch_all(
            """
            SELECT *
            FROM word_meanings
            WHERE lexicon_entry_id = (
                SELECT lexicon_entry_id FROM words WHERE word_id = %s
            )
            ORDER BY display_order, meaning_id
            """,
            (word_id,),
        )
        return [self._word_meaning_from_row(row) for row in rows]

    def save_user_word_meaning(
        self, user_id: int, meaning: UserWordMeaning
    ) -> None:
        owned = self._fetch_one(
            "SELECT 1 AS owned FROM words WHERE word_id = %s AND user_id = %s",
            (meaning.word_id, user_id),
        )
        if owned is None:
            raise ValueError("Word must belong to the user")
        if meaning.user_meaning_id is None:
            meaning._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO user_word_meanings (
                        word_id, korean_definition, english_definition, gloss,
                        display_order
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        meaning.word_id,
                        meaning.korean_definition,
                        meaning.english_definition,
                        meaning.gloss,
                        meaning.display_order,
                    ),
                )
            )
            return
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """
                UPDATE user_word_meanings
                SET korean_definition = %s, english_definition = %s, gloss = %s,
                    display_order = %s
                WHERE user_meaning_id = %s AND word_id = %s
                """,
                (
                    meaning.korean_definition,
                    meaning.english_definition,
                    meaning.gloss,
                    meaning.display_order,
                    meaning.user_meaning_id,
                    meaning.word_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("User meaning must belong to the word")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def list_user_word_meanings(self, word_id: int) -> list[UserWordMeaning]:
        rows = self._fetch_all(
            """
            SELECT *
            FROM user_word_meanings
            WHERE word_id = %s
            ORDER BY display_order, user_meaning_id
            """,
            (word_id,),
        )
        return [self._user_word_meaning_from_row(row) for row in rows]

    def delete_user_word_meaning(self, user_id: int, user_meaning_id: int) -> bool:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """
                DELETE FROM user_word_meanings
                WHERE user_meaning_id = %s
                  AND word_id IN (SELECT word_id FROM words WHERE user_id = %s)
                """,
                (user_meaning_id, user_id),
            )
            deleted = cursor.rowcount > 0
            self._connection.commit()
            return deleted
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def get_due_word_in_active_parts(
        self, user_id: int, due_at: datetime, exclude_word_id: int | None = None
    ) -> Word | None:
        row = self._fetch_one(
            """
            SELECT DISTINCT w.*, le.lemma, le.language, le.pos
            FROM words AS w
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            INNER JOIN doc_part_words AS dpw ON dpw.word_id = w.word_id
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE w.user_id = %s
              AND d.user_id = %s
              AND w.status IN (%s, %s, %s, %s)
              AND (w.due IS NULL OR w.due <= %s)
              AND dp.active = TRUE
              AND (%s IS NULL OR w.word_id <> %s)
            ORDER BY RAND()
            LIMIT 1
            """,
            (
                user_id,
                user_id,
                Status.NEW.name,
                Status.LEARNING.name,
                Status.REVIEW.name,
                Status.RELEARNING.name,
                self._datetime_to_mysql(due_at),
                exclude_word_id,
                exclude_word_id,
            ),
        )
        return None if row is None else self._word_from_row(row)

    def count_due_words_in_active_parts(
        self, user_id: int, due_at: datetime
    ) -> int:
        row = self._fetch_one(
            """
            SELECT COUNT(DISTINCT w.word_id) AS word_count
            FROM words AS w
            INNER JOIN doc_part_words AS dpw ON dpw.word_id = w.word_id
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE w.user_id = %s
              AND d.user_id = %s
              AND w.status IN (%s, %s, %s, %s)
              AND (w.due IS NULL OR w.due <= %s)
              AND dp.active = TRUE
            """,
            (
                user_id,
                user_id,
                Status.NEW.name,
                Status.LEARNING.name,
                Status.REVIEW.name,
                Status.RELEARNING.name,
                self._datetime_to_mysql(due_at),
            ),
        )
        return row["word_count"]

    def save_doc_part_word(self, association: DocPartWord) -> None:
        self._save_doc_part_word(association, commit=True)

    def _save_doc_part_word(
        self, association: DocPartWord, *, commit: bool
    ) -> None:
        if association.word.word_id is None or association.doc_part.doc_part_id is None:
            raise ValueError("Word and document part must be saved first")
        ownership = self._fetch_one(
            """
            SELECT 1
            FROM words AS w
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = %s
            INNER JOIN documents AS d ON d.document_id = dp.document_id
            WHERE w.word_id = %s
              AND w.user_id = d.user_id
            """,
            (association.doc_part.doc_part_id, association.word.word_id),
        )
        if ownership is None:
            raise ValueError("Word and document part must belong to the same user")
        self._execute_write(
            """
            INSERT INTO doc_part_words (word_id, doc_part_id, occurrences)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE occurrences = VALUES(occurrences)
            """,
            (
                association.word.word_id,
                association.doc_part.doc_part_id,
                association.occurrences,
            ),
            commit=commit,
        )

    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        rows = self._fetch_all(
            """
            SELECT dpw.occurrences, dp.doc_part_id, dp.text, dp.position,
                   dp.readability, dp.active, w.*,
                   le.lemma, le.language, le.pos
            FROM doc_part_words AS dpw
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN words AS w ON w.word_id = dpw.word_id
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE dpw.doc_part_id = %s
            ORDER BY w.word_id
            """,
            (doc_part_id,),
        )
        return [
            DocPartWord(
                word=self._word_from_row(row),
                doc_part=self._doc_part_from_row(row),
                occurrences=row["occurrences"],
            )
            for row in rows
        ]

    def list_users_doc_part_words(self, user_id: int) -> list[DocPartWord]:
        rows = self._fetch_all(
            """
            SELECT dpw.occurrences, dp.doc_part_id, dp.text, dp.position,
                   dp.readability, dp.active, w.*,
                   le.lemma, le.language, le.pos
            FROM documents AS d
            INNER JOIN doc_parts AS dp ON dp.document_id = d.document_id
            INNER JOIN doc_part_words AS dpw ON dpw.doc_part_id = dp.doc_part_id
            INNER JOIN words AS w ON w.word_id = dpw.word_id
            INNER JOIN lexicon_entries AS le
                ON le.lexicon_entry_id = w.lexicon_entry_id
            WHERE d.user_id = %s
            ORDER BY dp.doc_part_id, w.word_id
            """,
            (user_id,),
        )
        return [
            DocPartWord(
                word=self._word_study_from_row(row),
                doc_part=self._doc_part_from_row(row),
                occurrences=row["occurrences"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()

    def get_lexicon_version(self, source: str) -> str | None:
        row = self._fetch_one(
            "SELECT version FROM lexicon_metadata WHERE source = %s",
            (source,),
        )
        return None if row is None else row["version"]

    def install_lexicon(
        self,
        source: str,
        version: str,
        checksum: str,
        meanings: Iterable[tuple[str, Language, POS, WordMeaning]],
    ) -> None:
        try:
            self._execute_write(
                "DELETE FROM word_meanings WHERE source = %s",
                (source,),
                commit=False,
            )
            for lemma, language, pos, meaning in meanings:
                entry_id = self._ensure_lexicon_entry_values(lemma, language, pos)
                meaning._assign_id(
                    self._execute_insert(
                        """
                        INSERT INTO word_meanings (
                            lexicon_entry_id, source, korean_definition,
                            english_definition, gloss, display_order
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            entry_id,
                            source,
                            meaning.korean_definition,
                            meaning.english_definition,
                            meaning.gloss,
                            meaning.display_order,
                        ),
                        commit=False,
                    )
                )
            self._execute_write(
                """
                INSERT INTO lexicon_metadata (source, version, checksum)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    version = VALUES(version),
                    checksum = VALUES(checksum)
                """,
                (source, version, checksum),
                commit=False,
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
        self._execute_write(
            """
            INSERT INTO lexicon_entries (lemma, language, pos)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE lexicon_entry_id = LAST_INSERT_ID(lexicon_entry_id)
            """,
            (lemma, language.name, pos.name),
            commit=False,
        )
        row = self._fetch_one(
            """
            SELECT lexicon_entry_id
            FROM lexicon_entries
            WHERE lemma = %s AND language = %s AND pos = %s
            """,
            (lemma, language.name, pos.name),
        )
        return row["lexicon_entry_id"]

    def _execute_write(
        self,
        sql: str,
        parameters: tuple[Any, ...],
        *,
        commit: bool = True,
    ) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, parameters)
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def _execute_insert(
        self,
        sql: str,
        parameters: tuple[Any, ...],
        *,
        commit: bool = True,
    ) -> int:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, parameters)
            generated_id = cursor.lastrowid
            if commit:
                self._connection.commit()
            return generated_id
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def _execute_delete(self, sql: str, parameters: tuple[Any, ...]) -> bool:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, parameters)
            deleted = cursor.rowcount > 0
            self._connection.commit()
            return deleted
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def _fetch_one(
        self, sql: str, parameters: tuple[Any, ...]
    ) -> dict[str, Any] | None:
        cursor = self._connection.cursor(dictionary=True)
        try:
            cursor.execute(sql, parameters)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _fetch_all(
        self, sql: str, parameters: tuple[Any, ...]
    ) -> list[dict[str, Any]]:
        cursor = self._connection.cursor(dictionary=True)
        try:
            cursor.execute(sql, parameters)
            return cursor.fetchall()
        finally:
            cursor.close()

    def _document_from_row(self, row: dict[str, Any]) -> Document:
        document = Document(
            document_id=row["document_id"],
            title=row["title"],
            text=row["text"],
            language=Language[row["language"]],
            imported=self._as_date(row["imported"]),
        )
        document.doc_parts.extend(self.list_doc_parts(document.document_id))
        return document

    @staticmethod
    def _doc_part_from_row(row: dict[str, Any]) -> DocPart:
        return DocPart(
            doc_part_id=row["doc_part_id"],
            text=row["text"],
            position=row["position"],
            readability=float(row["readability"]),
            active=bool(row["active"]),
        )

    def _word_from_row(self, row: dict[str, Any]) -> Word:
        word = self._word_study_from_row(row)
        word.meanings.extend(self.list_word_meanings(word.word_id))
        word.user_meanings.extend(self.list_user_word_meanings(word.word_id))
        return word

    @staticmethod
    def _word_study_from_row(row: dict[str, Any]) -> Word:
        word = Word(
            word_id=row["word_id"],
            lemma=row["lemma"],
            language=Language[row["language"]],
            pos=POS[row["pos"]],
        )
        word.due = MySQLRepository._optional_datetime(row["due"])
        word.difficulty = float(row["difficulty"])
        word.stability = float(row["stability"])
        word.image_path = row["image_path"]
        word.status = Status[row["status"]]
        word.last_reviewed = MySQLRepository._optional_datetime(
            row["last_reviewed"]
        )
        word.step = row["step"]
        return word

    @staticmethod
    def _word_meaning_from_row(row: dict[str, Any]) -> WordMeaning:
        return WordMeaning(
            meaning_id=row["meaning_id"],
            korean_definition=row["korean_definition"],
            english_definition=row["english_definition"],
            gloss=row["gloss"],
            display_order=row["display_order"],
        )

    @staticmethod
    def _user_word_meaning_from_row(row: dict[str, Any]) -> UserWordMeaning:
        return UserWordMeaning(
            user_meaning_id=row["user_meaning_id"],
            word_id=row["word_id"],
            korean_definition=row["korean_definition"],
            english_definition=row["english_definition"],
            gloss=row["gloss"],
            display_order=row["display_order"],
        )

    @staticmethod
    def _as_date(value: date | str) -> date:
        return value if isinstance(value, date) else date.fromisoformat(value)

    @staticmethod
    def _optional_date(value: date | str | None) -> date | None:
        return None if value is None else MySQLRepository._as_date(value)

    @staticmethod
    def _datetime_to_mysql(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _mysql_to_datetime(value: datetime | str) -> datetime:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _optional_datetime(value: datetime | str | None) -> datetime | None:
        return None if value is None else MySQLRepository._mysql_to_datetime(value)
