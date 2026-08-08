from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any, Callable

from app.domain.document import DocPart, Document
from app.domain.enums import Language, MeaningFrequency, MeaningLabel, POS, Status
from app.domain.user import User
from app.domain.word import DocPartWord, Word, WordMeaning
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
                name VARCHAR(255) NOT NULL UNIQUE,
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
                due DATE NULL,
                difficulty DOUBLE NOT NULL DEFAULT 0.0,
                stability DOUBLE NOT NULL DEFAULT 0.0,
                image_path VARCHAR(1000) NULL,
                status VARCHAR(50) NOT NULL,
                last_reviewed DATE NULL,
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
                frequency VARCHAR(50) NOT NULL,
                display_order INT NOT NULL,
                CONSTRAINT fk_word_meanings_entry
                    FOREIGN KEY (lexicon_entry_id)
                    REFERENCES lexicon_entries(lexicon_entry_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS word_meaning_labels (
                meaning_id INT NOT NULL,
                label VARCHAR(50) NOT NULL,
                PRIMARY KEY (meaning_id, label),
                CONSTRAINT fk_word_meaning_labels_meaning
                    FOREIGN KEY (meaning_id) REFERENCES word_meanings(meaning_id)
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
                    INSERT INTO users (name, created, native_language)
                    VALUES (%s, %s, %s)
                    """,
                    (user.name, user.created, user.native_language.name),
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO users (user_id, name, created, native_language)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                created = VALUES(created),
                native_language = VALUES(native_language)
            """,
            (
                user.user_id,
                user.name,
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
            "SELECT user_id FROM users WHERE name = %s",
            (name,),
        )
        return None if row is None else self.get_user(row["user_id"])

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
                        image_path, status, last_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        lexicon_entry_id,
                        word.due,
                        word.difficulty,
                        word.stability,
                        word.image_path,
                        word.status.name,
                        word.last_reviewed,
                    ),
                    commit=commit,
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO words (
                word_id, user_id, lexicon_entry_id, due, difficulty,
                stability, image_path, status, last_reviewed
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                lexicon_entry_id = VALUES(lexicon_entry_id),
                due = VALUES(due),
                difficulty = VALUES(difficulty),
                stability = VALUES(stability),
                image_path = VALUES(image_path),
                status = VALUES(status),
                last_reviewed = VALUES(last_reviewed)
            """,
            (
                word.word_id,
                user_id,
                lexicon_entry_id,
                word.due,
                word.difficulty,
                word.stability,
                word.image_path,
                word.status.name,
                word.last_reviewed,
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
        return [self._word_from_row(row) for row in rows]

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
                        english_definition, gloss, frequency, display_order
                    )
                    VALUES (%s, 'USER', %s, %s, %s, %s, %s)
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
            self._execute_write(
                """
                INSERT INTO word_meanings (
                    meaning_id, lexicon_entry_id, source, korean_definition,
                    english_definition, gloss, frequency, display_order
                )
                VALUES (%s, %s, 'USER', %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    lexicon_entry_id = VALUES(lexicon_entry_id),
                    korean_definition = VALUES(korean_definition),
                    english_definition = VALUES(english_definition),
                    gloss = VALUES(gloss),
                    frequency = VALUES(frequency),
                    display_order = VALUES(display_order)
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
                commit=False,
            )
        self._execute_write(
            "DELETE FROM word_meaning_labels WHERE meaning_id = %s",
            (meaning.meaning_id,),
            commit=False,
        )
        for label in meaning.labels:
            self._execute_write(
                """
                INSERT INTO word_meaning_labels (meaning_id, label)
                VALUES (%s, %s)
                """,
                (meaning.meaning_id, label.name),
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
        meanings = [self._word_meaning_from_row(row) for row in rows]
        for meaning in meanings:
            labels = self._fetch_all(
                """
                SELECT label
                FROM word_meaning_labels
                WHERE meaning_id = %s
                ORDER BY label
                """,
                (meaning.meaning_id,),
            )
            meaning.labels.update(MeaningLabel[row["label"]] for row in labels)
        return meanings

    def list_learning_words_in_active_parts(self, user_id: int) -> list[Word]:
        rows = self._fetch_all(
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
              AND w.status = %s
              AND dp.active = TRUE
            ORDER BY w.word_id
            """,
            (user_id, user_id, Status.LEARNING.name),
        )
        return [self._word_from_row(row) for row in rows]

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
                            english_definition, gloss, frequency, display_order
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                for label in meaning.labels:
                    self._execute_write(
                        """
                        INSERT INTO word_meaning_labels (meaning_id, label)
                        VALUES (%s, %s)
                        """,
                        (meaning.meaning_id, label.name),
                        commit=False,
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
        word = Word(
            word_id=row["word_id"],
            lemma=row["lemma"],
            language=Language[row["language"]],
            pos=POS[row["pos"]],
        )
        word.due = MySQLRepository._optional_date(row["due"])
        word.difficulty = float(row["difficulty"])
        word.stability = float(row["stability"])
        word.image_path = row["image_path"]
        word.status = Status[row["status"]]
        word.last_reviewed = MySQLRepository._optional_date(row["last_reviewed"])
        word.meanings.extend(self.list_word_meanings(word.word_id))
        return word

    @staticmethod
    def _word_meaning_from_row(row: dict[str, Any]) -> WordMeaning:
        return WordMeaning(
            meaning_id=row["meaning_id"],
            korean_definition=row["korean_definition"],
            english_definition=row["english_definition"],
            gloss=row["gloss"],
            frequency=MeaningFrequency[row["frequency"]],
            display_order=row["display_order"],
        )

    @staticmethod
    def _as_date(value: date | str) -> date:
        return value if isinstance(value, date) else date.fromisoformat(value)

    @staticmethod
    def _optional_date(value: date | str | None) -> date | None:
        return None if value is None else MySQLRepository._as_date(value)
