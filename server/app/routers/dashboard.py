"""三角色看板数据"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import INNOVATE_KV
from app.models.database import GpaComp, Innovation, User, get_db
from app.security import get_current_user
from app.services.entity_registry import ENTITY_REGISTRY

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def _student_scope(db: AsyncSession, user: User):
    """数据权限范围：Student 看自己，Counsellor 看名下学生，Dean 看全部（None）"""
    if user.role == "Student":
        return select(User.id).where(User.id == user.id)
    if user.role == "Counsellor":
        return select(User.id).where(User.counsellorId == user.id)
    return None


@router.get("/student/pandect")
async def pandect(user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """学生学分全景：双创/实践饼图数据 + 距毕业要求差额 + 驳回提醒"""
    from app.services.credits import compute_pandect
    p = await compute_pandect(db, user.id)
    return {"code": 0, "data": p}


@router.get("/student/backlist")
async def backlist(user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    """驳回提醒：跨实体查询被驳回记录"""
    out = []
    for key, e in ENTITY_REGISTRY.items():
        rows = (await db.execute(select(e.model).where(
            e.model.sid == user.id, e.model.status == "驳回"
        ).order_by(e.model.createdAt.desc()))).scalars().all()
        for r in rows:
            title = next((getattr(r, f.name) for f in e.fields if f.name in
                          ("project", "team", "implementation")), "")
            out.append({"key": key, "label": e.label, "title": title,
                        "opinion": r.opinion, "auditTime": r.auditTime, "id": r.id})
    return {"code": 0, "data": out}


@router.get("/counsellor")
async def counsellor_dashboard(user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    sids = await _student_scope(db, user)
    out = []
    for key, e in ENTITY_REGISTRY.items():
        q = select(func.count()).select_from(e.model).where(e.model.status == "待审核")
        if sids is not None:
            q = q.where(e.model.sid.in_(sids))
        out.append({"key": key, "label": e.label, "group": e.group,
                    "count": (await db.execute(q)).scalar() or 0})
    return {"code": 0, "data": {"list": out}}


@router.get("/dean")
async def dean_dashboard(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """院长全局看板：规模统计 + 学分分布"""
    total_students = (await db.execute(select(func.count()).select_from(User)
                                       .where(User.role == "Student"))).scalar() or 0
    total_counsellors = (await db.execute(select(func.count()).select_from(User)
                                          .where(User.role == "Counsellor"))).scalar() or 0
    pending = approved = 0
    for e in ENTITY_REGISTRY.values():
        pending += (await db.execute(select(func.count()).select_from(e.model)
                                     .where(e.model.status == "待审核"))).scalar() or 0
        approved += (await db.execute(select(func.count()).select_from(e.model)
                                      .where(e.model.status == "通过"))).scalar() or 0

    inn_by_cat = []
    for cat, conf in INNOVATE_KV.items():
        credit = (await db.execute(select(func.coalesce(func.sum(Innovation.credit), 0))
                                   .where(Innovation.category == cat,
                                          Innovation.status == "通过"))).scalar() or 0
        inn_by_cat.append({"key": conf["label"], "value": round(float(credit), 2)})

    by_college = (await db.execute(
        select(User.college, func.count(User.id)).where(User.role == "Student")
        .group_by(User.college))).all()

    gpa_trend = []
    for sem, gpa in (await db.execute(
            select(GpaComp.semester, func.avg(GpaComp.gpa))
            .group_by(GpaComp.semester).order_by(GpaComp.semester))).all():
        gpa_trend.append({"key": sem, "value": round(float(gpa), 2)})

    return {"code": 0, "data": {
        "totalStudents": total_students, "totalCounsellors": total_counsellors,
        "pendingTotal": pending, "approvedTotal": approved,
        "innByCategory": inn_by_cat,
        "studentsByCollege": [{"key": c or "未分配", "value": n} for c, n in by_college],
        "avgGpaTrend": gpa_trend,
    }}
