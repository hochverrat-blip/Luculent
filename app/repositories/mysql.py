from __future__ import annotations

from datetime import date
from typing import Any, Callable

from app.domain.document import DocPart, Document
from app.domain.enums import Language, POS, Status
from app.domain.user import User
from app.domain.word import DocPartWord, Word
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
            CREATE TABLE IF NOT EXISTS words (
                word_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                lemma VARCHAR(500) NOT NULL,
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss VARCHAR(500) NOT NULL,
                due DATE NULL,
                difficulty DOUBLE NOT NULL DEFAULT 0.0,
                stability DOUBLE NOT NULL DEFAULT 0.0,
                image_path VARCHAR(1000) NULL,
                status VARCHAR(50) NOT NULL,
                last_reviewed DATE NULL,
                pos VARCHAR(50) NOT NULL,
                language VARCHAR(50) NOT NULL,
                CONSTRAINT fk_words_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
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
        if word.word_id is None:
            word._assign_id(
                self._execute_insert(
                    """
                    INSERT INTO words (
                        user_id, lemma, korean_definition, english_definition,
                        gloss, due, difficulty, stability, image_path, status,
                        last_reviewed, pos, language
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        user_id,
                        word.lemma,
                        word.korean_definition,
                        word.english_definition,
                        word.gloss,
                        word.due,
                        word.difficulty,
                        word.stability,
                        word.image_path,
                        word.status.name,
                        word.last_reviewed,
                        word.pos.name,
                        word.language.name,
                    ),
                )
            )
            return
        self._execute_write(
            """
            INSERT INTO words (
                word_id, user_id, lemma, korean_definition,
                english_definition, gloss, due, difficulty, stability,
                image_path, status, last_reviewed, pos, language
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                lemma = VALUES(lemma),
                korean_definition = VALUES(korean_definition),
                english_definition = VALUES(english_definition),
                gloss = VALUES(gloss),
                due = VALUES(due),
                difficulty = VALUES(difficulty),
                stability = VALUES(stability),
                image_path = VALUES(image_path),
                status = VALUES(status),
                last_reviewed = VALUES(last_reviewed),
                pos = VALUES(pos),
                language = VALUES(language)
            """,
            (
                word.word_id,
                user_id,
                word.lemma,
                word.korean_definition,
                word.english_definition,
                word.gloss,
                word.due,
                word.difficulty,
                word.stability,
                word.image_path,
                word.status.name,
                word.last_reviewed,
                word.pos.name,
                word.language.name,
            ),
        )

    def get_word(self, word_id: int) -> Word | None:
        row = self._fetch_one(
            "SELECT * FROM words WHERE word_id = %s",
            (word_id,),
        )
        return None if row is None else self._word_from_row(row)

    def list_words(self, user_id: int) -> list[Word]:
        rows = self._fetch_all(
            "SELECT * FROM words WHERE user_id = %s ORDER BY word_id",
            (user_id,),
        )
        return [self._word_from_row(row) for row in rows]

    def list_learning_words_in_active_parts(self, user_id: int) -> list[Word]:
        rows = self._fetch_all(
            """
            SELECT DISTINCT w.*
            FROM words AS w
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
        )

    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        rows = self._fetch_all(
            """
            SELECT dpw.occurrences, dp.doc_part_id, dp.text, dp.position,
                   dp.readability, dp.active, w.*
            FROM doc_part_words AS dpw
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN words AS w ON w.word_id = dpw.word_id
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

    @staticmethod
    def _word_from_row(row: dict[str, Any]) -> Word:
        word = Word(
            word_id=row["word_id"],
            lemma=row["lemma"],
            english_definition=row["english_definition"],
            language=Language[row["language"]],
            pos=POS[row["pos"]],
        )
        word.korean_definition = row["korean_definition"]
        word.gloss = row["gloss"]
        word.due = MySQLRepository._optional_date(row["due"])
        word.difficulty = float(row["difficulty"])
        word.stability = float(row["stability"])
        word.image_path = row["image_path"]
        word.status = Status[row["status"]]
        word.last_reviewed = MySQLRepository._optional_date(row["last_reviewed"])
        return word

    @staticmethod
    def _as_date(value: date | str) -> date:
        return value if isinstance(value, date) else date.fromisoformat(value)

    @staticmethod
    def _optional_date(value: date | str | None) -> date | None:
        return None if value is None else MySQLRepository._as_date(value)
