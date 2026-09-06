"""辅导员端学生管理 + 综合成绩"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import COLLEGE_MAJOR, PERIODS
from app.models.database import (GpaComp, Innovation, User, Voluntary, get_db)
from app.models.database import Practice as PracticeModel
from app.models.schemas import GpaCompIn, StudentCreate, StudentUpdate
from app.security import get_current_user, hash_password
from app.services.oplog import log_op

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
    """单个/批量新增学生（Excel 导入：前端解析后按行提交，服务端字典防呆 + 留痕）"""
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "无权操作")
    items = payload if isinstance(payload, list) else [payload]
    created, skipped, errors = [], [], []
    for i, item in enumerate(items, start=1):
        if not item.uid.strip() or not item.name.strip():
            errors.append({"row": i, "message": "学号或姓名为空"})
            continue
        # 导入防呆：年级/学院/专业必须命中业务字典（年级支持 "2023" 自动补 "级"）
        if item.periods:
            p = item.periods.strip()
            if p.isdigit() and len(p) == 4:
                p = f"{p}级"
            if p not in PERIODS:
                errors.append({"row": i, "message":
                               f"年级「{item.periods}」无效，应为 {' / '.join(PERIODS)}"})
                continue
            item.periods = p
        if item.college and item.college not in COLLEGE_MAJOR:
            errors.append({"row": i, "message":
                           f"学院「{item.college}」不在字典中（{(' / '.join(COLLEGE_MAJOR))}）"})
            continue
        if item.major and item.college in COLLEGE_MAJOR \
                and item.major not in COLLEGE_MAJOR[item.college]:
            errors.append({"row": i, "message":
                           f"学院「{item.college}」下无专业「{item.major}」"})
            continue
        exists = (await db.execute(select(User.id).where(User.uid == item.uid))).scalar_one_or_none()
        if exists:
            skipped.append(item.uid)
            continue
        if not item.sex:
            item.sex = "男"
        s = User(uid=item.uid, name=item.name, role="Student",
                 passwordHash=hash_password(item.password),
                 counsellorId=user.id if user.role == "Counsellor" else None,
                 **{k: v for k, v in item.model_dump().items()
                    if k not in ("uid", "name", "password") and v is not None})
        db.add(s)
        created.append(item.uid)
    if created:
        if len(items) > 1:
            summary = f"批量导入学生 {len(created)} 名" + \
                      (f"，跳过 {len(skipped)} 名（学号已存在）" if skipped else "")
        else:
            summary = f"新增学生 {items[0].name}（{items[0].uid}）"
        await log_op(db, user, "create", summary)
    await db.commit()
    return {"code": 0, "data": {"created": created, "skipped": skipped, "errors": errors}}


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


@gpa_router.post("/import")
async def gpa_import(payload: dict, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Excel 批量导入综合成绩：行内按「学号 + 学期」提交，学院/专业自动取自学生档案，重复学期跳过"""
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "无权操作")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "没有可导入的数据")
    uids = list({str(r.get("uid") or "").strip() for r in rows if r.get("uid")})
    stu_map: dict[str, User] = {}
    if uids:
        found = (await db.execute(
            select(User).where(User.uid.in_(uids), User.role == "Student"))).scalars().all()
        stu_map = {s.uid: s for s in found}
    created, errors = 0, []
    for i, raw in enumerate(rows, start=1):
        uid = str(raw.get("uid") or "").strip()
        stu = stu_map.get(uid)
        if stu is None:
            errors.append({"row": i, "message": f"学号「{uid or '空'}」不存在"})
            continue
        if user.role == "Counsellor" and stu.counsellorId != user.id:
            errors.append({"row": i, "message": f"{uid} 不在您的管理范围内"})
            continue
        semester = str(raw.get("semester") or "").strip()
        if not semester:
            errors.append({"row": i, "message": "学期不能为空"})
            continue
        dup = (await db.execute(select(GpaComp.id).where(
            GpaComp.sid == stu.id, GpaComp.semester == semester))).scalar_one_or_none()
        if dup:
            errors.append({"row": i, "message": f"{uid} {semester} 学期成绩已存在（跳过）"})
            continue
        try:
            db.add(GpaComp(sid=stu.id, semester=semester, college=stu.college or "",
                           major=stu.major or "",
                           mutual=float(raw["mutual"]), comp=float(raw["comp"]),
                           gpa=float(raw["gpa"]), gpaRank=int(float(raw["gpaRank"])),
                           compRank=int(float(raw["compRank"])), maxRank=int(float(raw["maxRank"]))))
        except (KeyError, TypeError, ValueError):
            errors.append({"row": i, "message": "成绩字段缺失或不是数字"})
            continue
        created += 1
    await db.commit()
    return {"code": 0, "data": {"created": created, "errors": errors}}


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
