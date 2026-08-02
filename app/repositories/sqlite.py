from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from app.domain.document import DocPart, Document
from app.domain.enums import Language, POS, Status
from app.domain.user import User
from app.domain.word import DocPartWord, Word
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
                name TEXT NOT NULL,
                created TEXT NOT NULL
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

            CREATE TABLE IF NOT EXISTS words (
                word_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lemma TEXT NOT NULL,
                korean_definition TEXT NOT NULL,
                english_definition TEXT NOT NULL,
                gloss TEXT NOT NULL,
                due TEXT,
                difficulty REAL NOT NULL DEFAULT 0.0,
                stability REAL NOT NULL DEFAULT 0.0,
                image_path TEXT,
                status TEXT NOT NULL,
                last_reviewed TEXT,
                pos TEXT NOT NULL,
                language TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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
                    "INSERT INTO users (name, created) VALUES (?, ?)",
                    (user.name, user.created.isoformat()),
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO users (user_id, name, created)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                created = excluded.created
            """,
            (user.user_id, user.name, user.created.isoformat()),
        )
        self._connection.commit()

    def get_user(self, user_id: int) -> User | None:
        row = self._connection.execute(
            "SELECT user_id, name, created FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        user = User(
            user_id=row["user_id"],
            name=row["name"],
            created=date.fromisoformat(row["created"]),
        )
        user.documents.extend(self.list_documents(user_id))
        user.words.extend(self.list_words(user_id))
        return user

    def save_document(self, user_id: int, document: Document) -> None:
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        word.lemma,
                        word.korean_definition,
                        word.english_definition,
                        word.gloss,
                        self._date_to_text(word.due),
                        word.difficulty,
                        word.stability,
                        word.image_path,
                        word.status.name,
                        self._date_to_text(word.last_reviewed),
                        word.pos.name,
                        word.language.name,
                    ),
                )
            )
            return
        self._connection.execute(
            """
            INSERT INTO words (
                word_id, user_id, lemma, korean_definition,
                english_definition, gloss, due, difficulty, stability,
                image_path, status, last_reviewed, pos, language
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word_id) DO UPDATE SET
                user_id = excluded.user_id,
                lemma = excluded.lemma,
                korean_definition = excluded.korean_definition,
                english_definition = excluded.english_definition,
                gloss = excluded.gloss,
                due = excluded.due,
                difficulty = excluded.difficulty,
                stability = excluded.stability,
                image_path = excluded.image_path,
                status = excluded.status,
                last_reviewed = excluded.last_reviewed,
                pos = excluded.pos,
                language = excluded.language
            """,
            (
                word.word_id,
                user_id,
                word.lemma,
                word.korean_definition,
                word.english_definition,
                word.gloss,
                self._date_to_text(word.due),
                word.difficulty,
                word.stability,
                word.image_path,
                word.status.name,
                self._date_to_text(word.last_reviewed),
                word.pos.name,
                word.language.name,
            ),
        )
        self._connection.commit()

    def get_word(self, word_id: int) -> Word | None:
        row = self._connection.execute(
            "SELECT * FROM words WHERE word_id = ?",
            (word_id,),
        ).fetchone()
        if row is None:
            return None
        return self._word_from_row(row)

    def list_words(self, user_id: int) -> list[Word]:
        rows = self._connection.execute(
            "SELECT * FROM words WHERE user_id = ? ORDER BY word_id",
            (user_id,),
        ).fetchall()
        return [self._word_from_row(row) for row in rows]

    def save_doc_part_word(self, association: DocPartWord) -> None:
        if association.word.word_id is None or association.doc_part.doc_part_id is None:
            raise ValueError("Word and document part must be saved first")
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
        self._connection.commit()

    def list_doc_part_words(self, doc_part_id: int) -> list[DocPartWord]:
        rows = self._connection.execute(
            """
            SELECT dpw.occurrences, dp.doc_part_id, dp.text, dp.position,
                   dp.readability, dp.active, w.*
            FROM doc_part_words AS dpw
            INNER JOIN doc_parts AS dp ON dp.doc_part_id = dpw.doc_part_id
            INNER JOIN words AS w ON w.word_id = dpw.word_id
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

    def _execute_insert(self, sql: str, parameters: tuple[object, ...]) -> int:
        cursor = self._connection.execute(sql, parameters)
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

    @staticmethod
    def _word_from_row(row: sqlite3.Row) -> Word:
        word = Word(
            word_id=row["word_id"],
            lemma=row["lemma"],
            english_definition=row["english_definition"],
            language=Language[row["language"]],
            pos=POS[row["pos"]],
        )
        word.korean_definition = row["korean_definition"]
        word.gloss = row["gloss"]
        word.due = SQLiteRepository._text_to_date(row["due"])
        word.difficulty = row["difficulty"]
        word.stability = row["stability"]
        word.image_path = row["image_path"]
        word.status = Status[row["status"]]
        word.last_reviewed = SQLiteRepository._text_to_date(row["last_reviewed"])
        return word

    @staticmethod
    def _date_to_text(value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _text_to_date(value: str | None) -> date | None:
        return date.fromisoformat(value) if value is not None else None
