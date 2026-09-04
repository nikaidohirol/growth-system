"""JWT 认证与 RBAC 依赖"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import User, get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "uid": user.uid,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    if cred is None:
        raise exc
    try:
        payload = jwt.decode(cred.credentials, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise exc
    user = await db.get(User, payload.get("sub"))
    if user is None:
        raise exc
    return user


def require_roles(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="无权访问该资源")
        return user
    return checker


StudentDep = Depends(require_roles("Student"))
ReviewerDep = Depends(require_roles("Counsellor", "Dean"))
AdminDep = Depends(require_roles("Dean"))


async def get_user_by_uid(db: AsyncSession, uid: str) -> User | None:
    return (await db.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
