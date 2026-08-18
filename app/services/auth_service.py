from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User


class AuthService:
    def get_user_by_email(self, db: Session, email: str) -> User | None:
        statement = select(User).where(User.email == email.lower())
        return db.execute(statement).scalar_one_or_none()

    def authenticate_user(self, db: Session, email: str, password: str) -> User | None:
        user = self.get_user_by_email(db, email)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


auth_service = AuthService()
