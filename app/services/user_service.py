from app.domain import User
from app.services.base_service import Service


class UserService(Service):
    def new_user(self, username: str) -> User:
        username = self._validated_username(username)
        if self._repository.get_user_by_name(username) is not None:
            raise ValueError(f"User already exists: {username}")
        user = User(None, username)
        self._repository.save_user(user)
        return user

    def get_user(self, username: str) -> User | None:
        return self._repository.get_user_by_name(self._validated_username(username))

    def get_users(self) -> list[User]:
        return self._repository.list_users()

    def delete_user(self, user: User) -> bool:
        if user.user_id is None:
            raise ValueError("User must be saved before deletion")
        return self._repository.delete_user(user.user_id)

    @staticmethod
    def _validated_username(username: str) -> str:
        username = username.strip()
        if not username:
            raise ValueError("Username is required")
        return username
