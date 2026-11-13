from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.JWT_HOURS)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, config.JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(401, "Sign in first")
    try:
        data = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Sign in again.") from None
    user = db.get(User, int(data["sub"]))
    if user is None:
        raise HTTPException(401, "Account not found")
    return user


def ta_only(user: User = Depends(current_user)) -> User:
    if user.role != "ta":
        raise HTTPException(403, "Only TAs can do this")
    return user


def student_only(user: User = Depends(current_user)) -> User:
    if user.role != "student":
        raise HTTPException(403, "Only students can do this")
    return user
