"""辅导员端学生管理 + 综合成绩"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (GpaComp, Innovation, User, Voluntary, get_db)
from app.models.database import Practice as PracticeModel
from app.models.schemas import GpaCompIn, StudentCreate, StudentUpdate
from app.security import get_current_user, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


async def _check_scope(db: AsyncSession, user: User, sid: str):
    if user.role == "Dean":
        return
    target = await db.get(User, sid)
    if target is None or target.counsellorId != user.id:
        raise HTTPException(403, "该学生不在您的管理范围内")


@router.get("/students")
async def list_students(periods: str = "", classId: str = "", keyword: str = "",
                        page: int = Query(1, ge=1), pageSize: int = Query(10, ge=1, le=100),
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if user.role == "Student":
        raise HTTPException(403, "无权访问")
    q = select(User).where(User.role == "Student")
    if user.role == "Counsellor":
        q = q.where(User.counsellorId == user.id)
    if periods:
        q = q.where(User.periods == periods)
    if classId:
        q = q.where(User.classId == classId)
    if keyword:
        q = q.where(or_(User.name.like(f"%{keyword}%"), User.uid.like(f"%{keyword}%"),
                        cast(User.classId, String).like(f"%{keyword}%")))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    students = (await db.execute(
        q.order_by(User.uid).offset((page - 1) * pageSize).limit(pageSize))).scalars().all()

    out = []
    for s in students:
        credits = await _student_credits(db, s.id)
        out.append({
            "id": s.id, "uid": s.uid, "name": s.name, "sex": s.sex, "classId": s.classId,
            "periods": s.periods, "college": s.college, "major": s.major,
            "phone": s.phone, "email": s.email, "politicsStatus": s.politicsStatus,
            **credits,
        })
    return {"code": 0, "data": {"list": out, "total": total, "page": page, "pageSize": pageSize}}


async def _student_credits(db: AsyncSession, sid: str) -> dict:
    rows = (await db.execute(select(Innovation).where(
        Innovation.sid == sid, Innovation.status == "通过"))).scalars().all()
    inn = round(sum(r.credit or 0 for r in rows), 2)
    pra_count = len((await db.execute(select(PracticeModel.id).where(
        PracticeModel.sid == sid, PracticeModel.status == "通过"))).all())
    vol = 0
    for v in (await db.execute(select(Voluntary.duration).where(
            Voluntary.sid == sid, Voluntary.status == "通过"))).scalars():
        vol += v or 0
    pra = round(min(pra_count * 0.5, 1) + min(vol // 20 * 0.5, 1), 2)
    return {"innCredit": inn, "praCredit": pra, "sumCredit": round(inn + pra, 2)}


@router.post("/students")
async def add_students(payload: list[StudentCreate] | StudentCreate,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "无权操作")
    items = payload if isinstance(payload, list) else [payload]
    created, skipped = [], []
    for item in items:
        exists = (await db.execute(select(User.id).where(User.uid == item.uid))).scalar_one_or_none()
        if exists:
            skipped.append(item.uid)
            continue
        s = User(uid=item.uid, name=item.name, role="Student",
                 passwordHash=hash_password(item.password),
                 counsellorId=user.id if user.role == "Counsellor" else None,
                 **{k: v for k, v in item.model_dump().items()
                    if k not in ("uid", "name", "password") and v is not None})
        db.add(s)
        created.append(item.uid)
    await db.commit()
    return {"code": 0, "data": {"created": created, "skipped": skipped}}


@router.put("/students/{sid}")
async def update_student(sid: str, payload: StudentUpdate,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await _check_scope(db, user, sid)
    s = await db.get(User, sid)
    if s is None:
        raise HTTPException(404, "学生不存在")
    for k, v in payload.model_dump().items():
        if v is not None:
            setattr(s, k, v)
    await db.commit()
    return {"code": 0}


@router.delete("/students/{sid}")
async def delete_student(sid: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await _check_scope(db, user, sid)
    s = await db.get(User, sid)
    if s is None:
        raise HTTPException(404, "学生不存在")
    await db.delete(s)
    await db.commit()
    return {"code": 0}


# ---- 综合素质成绩 ----
gpa_router = APIRouter(prefix="/api/gpa", tags=["gpa"])


@gpa_router.get("/my")
async def my_gpa(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GpaComp).where(GpaComp.sid == user.id)
                             .order_by(GpaComp.semester))).scalars().all()
    return {"code": 0, "data": [{
        "id": r.id, "semester": r.semester, "college": r.college, "major": r.major,
        "mutual": r.mutual, "comp": r.comp, "gpa": r.gpa,
        "gpaRank": r.gpaRank, "compRank": r.compRank, "maxRank": r.maxRank,
    } for r in rows]}


@gpa_router.get("/list")
async def gpa_list(sid: str, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if user.role == "Student":
        raise HTTPException(403, "无权访问")
    await _check_scope(db, user, sid)
    rows = (await db.execute(select(GpaComp).where(GpaComp.sid == sid)
                             .order_by(GpaComp.semester))).scalars().all()
    return {"code": 0, "data": [{
        "id": r.id, "semester": r.semester, "mutual": r.mutual, "comp": r.comp,
        "gpa": r.gpa, "gpaRank": r.gpaRank, "compRank": r.compRank, "maxRank": r.maxRank,
    } for r in rows]}


@gpa_router.post("")
async def gpa_add(payload: GpaCompIn, user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "无权操作")
    await _check_scope(db, user, payload.sid)
    db.add(GpaComp(**payload.model_dump()))
    await db.commit()
    return {"code": 0}


@gpa_router.delete("/{row_id}")
async def gpa_del(row_id: str, user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "无权操作")
    row = await db.get(GpaComp, row_id)
    if row:
        await _check_scope(db, user, row.sid)
        await db.delete(row)
        await db.commit()
    return {"code": 0}
