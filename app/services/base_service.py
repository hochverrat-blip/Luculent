from __future__ import annotations

from app.repositories import Repository, create_repository


class Service:
    def __init__(self) -> None:
        self._repository: Repository = create_repository()

    def close(self) -> None:
        self._repository.close()

    def __enter__(self) -> Service:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
