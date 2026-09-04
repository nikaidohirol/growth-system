"""审核中心 — 辅导员/院长统一审核所有实体（注册表分发）"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, get_db
from app.models.schemas import AuditSubmitReq
from app.security import get_current_user
from app.routers.entities import get_def, serialize
from app.services.entity_registry import ENTITY_REGISTRY

router = APIRouter(prefix="/api/audit", tags=["audit"])


async def scope_sids(db: AsyncSession, user: User):
    """数据权限：辅导员只看自己名下学生，院长看全部"""
    if user.role == "Dean":
        return None
    return select(User.id).where(User.counsellorId == user.id)


@router.get("/summary")
async def summary(user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """各实体待审核数量汇总（辅导员 dashboard / 审核中心 tab 角标）"""
    sids = await scope_sids(db, user)
    out, pending_total = [], 0
    for key, e in ENTITY_REGISTRY.items():
        q = select(func.count()).select_from(e.model).where(e.model.status == "待审核")
        if sids is not None:
            q = q.where(e.model.sid.in_(sids))
        n = (await db.execute(q)).scalar() or 0
        pending_total += n
        out.append({"key": key, "label": e.label, "group": e.group, "count": n})
    approved = 0
    for key, e in ENTITY_REGISTRY.items():
        q = select(func.count()).select_from(e.model).where(e.model.status == "通过")
        if sids is not None:
            q = q.where(e.model.sid.in_(sids))
        approved += (await db.execute(q)).scalar() or 0
    return {"code": 0, "data": {"list": out, "pendingTotal": pending_total,
                                "approvedTotal": approved}}


@router.get("/records")
async def records(key: str, status: str = "待审核",
                  page: int = Query(1, ge=1), pageSize: int = Query(10, ge=1, le=100),
                  keyword: str = "",
                  user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """按实体类型拉取审核列表（含学生信息）"""
    e = get_def(key)
    sids = await scope_sids(db, user)
    q = select(e.model, User).join(User, e.model.sid == User.id)
    if sids is not None:
        q = q.where(e.model.sid.in_(sids))
    if status and status != "全部":
        q = q.where(e.model.status == status)
    if keyword:
        q = q.where(User.name.like(f"%{keyword}%") | User.uid.like(f"%{keyword}%"))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.order_by(e.model.createdAt.desc()).offset((page - 1) * pageSize).limit(pageSize)
    )).all()
    lst = [{**serialize(r, e), "student": {"uid": u.uid, "name": u.name,
            "classId": u.classId, "college": u.college}} for r, u in rows]
    return {"code": 0, "data": {"list": lst, "total": total, "page": page, "pageSize": pageSize}}


@router.post("/submit/{key}/{row_id}")
async def submit(key: str, row_id: str, req: AuditSubmitReq,
                 user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await db.get(e.model, row_id)
    if row is None:
        raise HTTPException(404, "记录不存在")
    sids = await scope_sids(db, user)
    if sids is not None and row.sid not in (await db.execute(sids)).scalars().all():
        raise HTTPException(403, "该学生不在您的管理范围内")
    row.status = req.status
    row.auditor = user.name
    row.opinion = req.opinion or req.status
    from app.models.database import now
    row.auditTime = now().strftime("%Y-%m-%d %H:%M:%S")
    await db.commit()
    return {"code": 0, "data": serialize(row, e)}
