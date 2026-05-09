"""JWT authentication dependency."""

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate a Bearer JWT, check required claims, and return the authenticated User."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET not configured")
    try:
        payload = jwt.decode(credentials.credentials, secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    if "exp" not in payload:
        raise HTTPException(status_code=401, detail="Token missing 'exp' claim")
    user = db.query(User).filter(User.email == sub).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user not found")
    return user
