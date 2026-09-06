"""三角色看板数据"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import INNOVATE_KV
from app.models.database import GpaComp, Innovation, User, get_db
from app.security import get_current_user
from app.services.entity_registry import ENTITY_REGISTRY, category_scope

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
        q = select(e.model).where(e.model.sid == user.id, e.model.status == "驳回")
        cat = category_scope(key, e.model)
        if cat is not None:
            q = q.where(cat)
        rows = (await db.execute(q.order_by(e.model.createdAt.desc()))).scalars().all()
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
        cat = category_scope(key, e.model)
        if cat is not None:
            q = q.where(cat)
        if sids is not None:
            q = q.where(e.model.sid.in_(sids))
        out.append({"key": key, "label": e.label, "group": e.group,
                    "count": (await db.execute(q)).scalar() or 0})
    return {"code": 0, "data": {"list": out}}


@router.get("/student/comp-forecast")
async def comp_forecast_me(user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """本人综测过程分测算：只统计已生效记录，分项明细逐条可追溯"""
    if user.role != "Student":
        raise HTTPException(403, "仅学生可查看本人测算")
    from app.services.comp_score import forecast
    lst = await forecast(db, select(User.id).where(User.id == user.id))
    return {"code": 0, "data": lst[0] if lst else None}


@router.get("/comp-forecast")
async def comp_forecast(major: str = "", periods: str = "",
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """综测测算专业排名表：辅导员限名下学生（年级×专业带班），院长全院；可按年级/专业过滤。
    排名口径为同年级同专业（总分从高到低顺序编号）；测算总分与教务导入综测并列展示"""
    if user.role == "Student":
        raise HTTPException(403, "学生请使用本人测算接口")
    conds = []
    if user.role == "Counsellor":
        conds.append(User.counsellorId == user.id)
    if major:
        conds.append(User.major == major)
    if periods:
        conds.append(User.periods == periods)
    from app.services.comp_score import forecast
    lst = await forecast(db, select(User.id).where(*conds) if conds else None)
    return {"code": 0, "data": {"list": lst}}


@router.get("/dean")
async def dean_dashboard(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """院长院系看板：本院规模统计 + 学分/GPA 分布（按院长所属学院收窄；学院缺失时回退全校）"""
    college = user.college
    college_scope = (User.college == college) if college else true()
    gpa_scope = (GpaComp.college == college) if college else true()
    sids_q = select(User.id).where(User.role == "Student", college_scope)

    total_students = (await db.execute(select(func.count()).select_from(User)
                                       .where(User.role == "Student", college_scope))).scalar() or 0
    total_counsellors = (await db.execute(select(func.count()).select_from(User)
                                          .where(User.role == "Counsellor", college_scope))).scalar() or 0
    pending = dean_pending = public_n = approved = 0
    for key, e in ENTITY_REGISTRY.items():
        cat = category_scope(key, e.model)
        for st in ("待审核", "待院长审批", "公示中", "通过"):
            conds = [e.model.status == st, e.model.sid.in_(sids_q)] + ([cat] if cat is not None else [])
            n = (await db.execute(select(func.count()).select_from(e.model)
                                  .where(*conds))).scalar() or 0
            if st == "待审核":
                pending += n
            elif st == "待院长审批":
                dean_pending += n
            elif st == "公示中":
                public_n += n
            else:
                approved += n

    # 各辅导员初审通过率：其名下学生记录中「初审通过（通过/公示中/待院长审批）」占比（宏观监督）
    counsellors = {c.id: c for c in (await db.execute(
        select(User).where(User.role == "Counsellor", college_scope))).scalars().all()}
    stat = {cid: {"passed": 0, "rejected": 0} for cid in counsellors}
    for key, e in ENTITY_REGISTRY.items():
        cat = category_scope(key, e.model)
        conds = [e.model.sid.in_(sids_q)] + ([cat] if cat is not None else [])
        rows = (await db.execute(
            select(User.counsellorId, e.model.status, func.count())
            .join(User, User.id == e.model.sid).where(*conds)
            .group_by(User.counsellorId, e.model.status))).all()
        for cid, st, n in rows:
            if cid not in stat:
                continue
            if st in ("通过", "公示中", "待院长审批"):
                stat[cid]["passed"] += n
            elif st == "驳回":
                stat[cid]["rejected"] += n
    counsellor_stats = []
    for cid, c in counsellors.items():
        passed, rejected = stat[cid]["passed"], stat[cid]["rejected"]
        total = passed + rejected
        counsellor_stats.append({"name": c.name, "total": total, "passed": passed,
                                 "rate": round(passed / total, 4) if total else 0.0})

    inn_by_cat = []
    for cat, conf in INNOVATE_KV.items():
        credit = (await db.execute(select(func.coalesce(func.sum(Innovation.credit), 0))
                                   .where(Innovation.category == cat,
                                          Innovation.status == "通过",
                                          Innovation.sid.in_(sids_q)))).scalar() or 0
        inn_by_cat.append({"key": conf["label"], "value": round(float(credit), 2)})

    by_grade = (await db.execute(
        select(User.periods, func.count(User.id)).where(User.role == "Student", college_scope)
        .group_by(User.periods).order_by(User.periods))).all()

    gpa_trend = []
    for sem, gpa in (await db.execute(
            select(GpaComp.semester, func.avg(GpaComp.gpa)).where(gpa_scope)
            .group_by(GpaComp.semester).order_by(GpaComp.semester))).all():
        gpa_trend.append({"key": sem, "value": round(float(gpa), 2)})

    return {"code": 0, "data": {
        "totalStudents": total_students, "totalCounsellors": total_counsellors,
        "pendingTotal": pending, "approvedTotal": approved, "deanPendingTotal": dean_pending,
        "publicTotal": public_n, "counsellorStats": counsellor_stats,
        "innByCategory": inn_by_cat,
        "studentsByGrade": [{"key": g or "未分配", "value": n} for g, n in by_grade],
        "avgGpaTrend": gpa_trend,
    }}
