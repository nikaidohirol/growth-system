"""教育经历 + 成长档案聚合（A4 导出页一次拉全）"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import bump
from app.models.database import (Base, Certificate, Experience, GpaComp, Honor,
                                 Innovation, Organization, Party, User,
                                 Voluntary, get_db)
from app.models.database import Practice as PracticeModel
from app.models.schemas import ExperienceIn
from app.security import get_current_user
from app.services.entity_registry import ENTITY_REGISTRY, INN_CATEGORY

router = APIRouter(tags=["experience"])


async def _resolve_target(db: AsyncSession, user: User, sid: str) -> str:
    """查看目标：默认本人；辅导员/院长指定 sid 时必须过带班 scope（与 gpa_list 同口径）"""
    if user.role in ("Counsellor", "Dean") and sid:
        from app.routers.users import _check_scope
        await _check_scope(db, user, sid)
        return sid
    return user.id


@router.get("/api/experience")
async def list_experience(sid: str = "", user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    target = await _resolve_target(db, user, sid)
    rows = (await db.execute(select(Experience).where(Experience.sid == target)
                             .order_by(Experience.startDate))).scalars().all()
    return {"code": 0, "data": [{
        "id": r.id, "startDate": r.startDate, "endDate": r.endDate,
        "college": r.college, "major": r.major, "classId": r.classId,
        "eyewitness": r.eyewitness} for r in rows]}


@router.post("/api/experience")
async def add_experience(payload: ExperienceIn, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    db.add(Experience(sid=user.id, **payload.model_dump()))
    await db.commit()
    return {"code": 0}


@router.put("/api/experience/{row_id}")
async def update_experience(row_id: str, payload: ExperienceIn,
                            user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    row = await db.get(Experience, row_id)
    if row is None or row.sid != user.id:
        raise HTTPException(404, "记录不存在")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await db.commit()
    return {"code": 0}


@router.delete("/api/experience/{row_id}")
async def delete_experience(row_id: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    row = await db.get(Experience, row_id)
    if row is None or row.sid != user.id:
        raise HTTPException(404, "记录不存在")
    await db.delete(row)
    await db.commit()
    bump()
    return {"code": 0}


@router.get("/api/export/dossier")
async def dossier(sid: str = "", user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """成长档案：一次聚合 A4 导出页所需全部数据（默认仅含审核通过项）"""
    target = await _resolve_target(db, user, sid)
    stu = await db.get(User, target)
    if stu is None:
        raise HTTPException(404, "学生不存在")

    async def approved(model: type[Base]):
        return (await db.execute(select(model).where(
            model.sid == target, model.status == "通过"
        ).order_by(model.createdAt))).scalars().all()

    def dump(e, items) -> list[dict]:
        return [{f.name: getattr(r, f.name, None) for f in e.fields} for r in items]

    inn = (await db.execute(select(Innovation).where(
        Innovation.sid == target, Innovation.status == "通过"))).scalars().all()
    innovations = {cat: dump(ENTITY_REGISTRY[f"inn_{cat}"],
                             [r for r in inn if r.category == cat])
                   for cat in INN_CATEGORY.values()}

    exp_rows = (await db.execute(select(Experience).where(
        Experience.sid == target).order_by(Experience.startDate))).scalars().all()
    gpa_rows = (await db.execute(select(GpaComp).where(
        GpaComp.sid == target).order_by(GpaComp.semester))).scalars().all()
    party_rows = (await db.execute(select(Party).where(
        Party.sid == target).order_by(Party.date))).scalars().all()

    return {"code": 0, "data": {
        "student": {
            "uid": stu.uid, "name": stu.name, "sex": stu.sex, "nation": stu.nation,
            "politicsStatus": stu.politicsStatus, "birthday": stu.birthday,
            "classId": stu.classId, "periods": stu.periods,
            "college": stu.college, "major": stu.major,
            "origin": stu.origin, "photo": stu.photo,
        },
        "experiences": [{"startDate": r.startDate, "endDate": r.endDate,
                         "college": r.college, "major": r.major, "classId": r.classId}
                        for r in exp_rows],
        "gpaList": [{"semester": r.semester, "gpa": r.gpa, "comp": r.comp,
                     "gpaRank": r.gpaRank, "compRank": r.compRank, "maxRank": r.maxRank}
                    for r in gpa_rows],
        "parties": dump(ENTITY_REGISTRY["party"], party_rows),
        "organizations": dump(ENTITY_REGISTRY["organization"], await approved(Organization)),
        "honors": dump(ENTITY_REGISTRY["honor"], await approved(Honor)),
        "certificates": dump(ENTITY_REGISTRY["certificate"], await approved(Certificate)),
        "voluntarys": dump(ENTITY_REGISTRY["voluntary"], await approved(Voluntary)),
        "practices": dump(ENTITY_REGISTRY["practice"], await approved(PracticeModel)),
        "innovations": innovations,
    }}
