from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Admin

hasher = PasswordHasher()
settings = get_settings()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_token(admin: Admin) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    return jwt.encode({"sub": admin.id, "exp": expires, "type": "session"}, settings.session_secret, algorithm="HS256")


def current_admin(booking_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> Admin:
    if not booking_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        payload = jwt.decode(booking_session, settings.session_secret, algorithms=["HS256"])
        if payload.get("type") != "session":
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    admin = db.get(Admin, payload.get("sub"))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return admin

