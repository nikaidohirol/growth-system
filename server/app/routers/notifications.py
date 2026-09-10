"""站内通知 — 私人消息中心（列表/未读数/已读标记），仅按登录人 uid 查询"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Notification, User, get_db
from app.security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(n: Notification) -> dict:
    return {"id": n.id, "title": n.title, "content": n.content, "type": n.type,
            "linkKey": n.linkKey, "linkId": n.linkId, "isRead": n.isRead,
            "createdAt": n.createdAt}


async def _unread_count(db: AsyncSession, uid: str) -> int:
    return (await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.uid == uid, Notification.isRead.is_(False)),
    )).scalar() or 0


@router.get("")
async def list_notifications(user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db),
                             page: int = Query(1, ge=1),
                             pageSize: int = Query(10, ge=1, le=50),
                             unread: bool = False):
    """本人通知列表（含未读总数；unread=true 只看未读）"""
    q = select(Notification).where(Notification.uid == user.uid)
    if unread:
        q = q.where(Notification.isRead.is_(False))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.order_by(Notification.createdAt.desc(), Notification.id.desc())
        .offset((page - 1) * pageSize).limit(pageSize))).scalars().all()
    return {"code": 0, "data": {"list": [_serialize(n) for n in rows], "total": total,
                                "unread": await _unread_count(db, user.uid),
                                "page": page, "pageSize": pageSize}}


@router.get("/unread")
async def unread(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    """轻量未读数（前端铃铛轮询用）"""
    return {"code": 0, "data": {"unread": await _unread_count(db, user.uid)}}


@router.post("/read")
async def mark_read(payload: dict, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    """标记已读：{ids: [...]} 单条/批量，或 {all: true} 全部"""
    q = update(Notification).where(Notification.uid == user.uid)
    if payload.get("all"):
        q = q.values(isRead=True)
    else:
        ids = [i for i in (payload.get("ids") or []) if isinstance(i, str)]
        if not ids:
            return {"code": 0}
        q = q.where(Notification.id.in_(ids)).values(isRead=True)
    await db.execute(q)
    await db.commit()
    return {"code": 0}


@router.post("/clear")
async def clear_notifications(user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """清空本人全部通知（不可恢复，仅作用本人）"""
    await db.execute(delete(Notification).where(Notification.uid == user.uid))
    await db.commit()
    return {"code": 0}
