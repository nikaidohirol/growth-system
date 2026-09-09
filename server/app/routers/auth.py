"""认证与个人中心"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, get_db
from app.models.schemas import LoginReq, PasswordChange, UserOut
from app.security import (create_access_token, get_current_user, hash_password,
                          verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def to_user_out(db: AsyncSession, user: User) -> UserOut:
    counsellor_name = None
    if user.counsellorId:
        c = await db.get(User, user.counsellorId)
        counsellor_name = c.name if c else None
    out = UserOut.model_validate(user)
    out.counsellorName = counsellor_name
    return out


@router.post("/login")
async def login(req: LoginReq, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.uid == req.uid))).scalar_one_or_none()
    if user is None or not verify_password(req.password, user.passwordHash):
        raise HTTPException(401, "账号或密码错误")
    from app.services.oplog import log_op
    await log_op(db, user, "login", f"{user.role}「{user.name}」登录系统")
    await db.commit()
    token = create_access_token(user)
    return {"code": 0, "data": {"token": token, "user": await to_user_out(db, user)}}


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"code": 0, "data": await to_user_out(db, user)}


@router.put("/me")
async def update_me(payload: dict, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    allowed = ["name", "phone", "email", "sex", "nation", "birthday",
               "politicsStatus", "origin", "address", "photo", "title"]
    for k, v in payload.items():
        if k in allowed:
            if v is not None and (not isinstance(v, str) or len(v) > 255):
                raise HTTPException(400, f"字段 {k} 类型或长度不合法")
            setattr(user, k, v)
    await db.commit()
    return {"code": 0, "data": await to_user_out(db, user)}


@router.put("/password")
async def change_password(payload: PasswordChange, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(payload.oldPassword, user.passwordHash):
        raise HTTPException(400, "原密码错误")
    user.passwordHash = hash_password(payload.newPassword)
    await db.commit()
    return {"code": 0}
