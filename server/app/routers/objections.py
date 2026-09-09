"""公示异议 — 公示期监督闭环：公示栏 → 实名异议 → 院长复核（成立驳回 / 不成立维持）

设计要点：
- 公示的本意是阳光监督：公示栏聚合全院「公示中」记录，所有登录用户可见可查
- 异议实名：记录归属学生本人不可对自己的记录提异议（有疑问联系辅导员即可）；
  同一人对同一记录存在未复核异议时防重复提交
- 复核二选一：成立 → 记录驳回（复用 audit._reject 留痕 + 通知归属学生）／不成立 → 维持认定
- 挂着「待复核」异议的公示记录暂停惰性晋升（audit_flow.promote_expired），杜绝「有人异议却自动生效」
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import bump
from app.models.database import Objection, User, get_db, now
from app.routers.audit import _dean_recipients, _reject, scope_sids
from app.routers.entities import get_def, serialize
from app.security import get_current_user
from app.services.audit_flow import STATUS_PUBLIC
from app.services.entity_registry import ENTITY_REGISTRY, category_scope
from app.services.notify import notify
from app.services.oplog import log_op, record_title

router = APIRouter(prefix="/api/objections", tags=["objections"])


def _obj_dict(o: Objection) -> dict:
    return {"id": o.id, "key": o.key, "recordId": o.recordId, "label": o.recordLabel,
            "title": o.recordTitle, "reason": o.reason, "status": o.status,
            "objector": {"uid": o.objectorUid, "name": o.objectorName},
            "handledBy": o.handledBy, "handledTime": o.handledTime, "createdAt": o.createdAt}


@router.get("/publicity")
async def publicity(user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    """公示栏：全院「公示中」记录聚合（登录即可见——公示即阳光监督），按公示截止时间升序"""
    out = []
    for key, e in ENTITY_REGISTRY.items():
        q = (select(e.model, User).join(User, e.model.sid == User.id)
             .where(e.model.status == STATUS_PUBLIC))
        cat = category_scope(key, e.model)
        if cat is not None:
            q = q.where(cat)
        for r, u in (await db.execute(q.order_by(e.model.publicEnd.asc()).limit(200))).all():
            out.append({"key": key, "recordId": r.id, "label": e.label,
                        "title": record_title(e, serialize(r, e)),
                        "credit": getattr(r, "credit", None), "sid": r.sid,
                        "publicEnd": r.publicEnd,
                        "student": {"name": u.name, "classId": u.classId}})
    out.sort(key=lambda x: x["publicEnd"] or "")
    return {"code": 0, "data": {"list": out, "total": len(out)}}


@router.post("")
async def submit(payload: dict, user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    """实名异议：必填理由；归属学生本人不可异议自己；未复核的重复异议拦截"""
    e = get_def(str(payload.get("key") or ""))
    record_id = str(payload.get("recordId") or "")
    reason = str(payload.get("reason") or "").strip()
    if not record_id:
        raise HTTPException(400, "缺少记录标识")
    if len(reason) < 5:
        raise HTTPException(400, "请填写异议理由（至少 5 个字），以便学院核实")
    row = await db.get(e.model, record_id)
    if row is None or row.status != STATUS_PUBLIC:
        raise HTTPException(400, "该记录不在公示期，无法提出异议")
    if row.sid == user.id:
        raise HTTPException(400, "不可对自己的认定记录提出异议，如有疑问请联系辅导员")
    dup = (await db.execute(select(Objection.id).where(
        Objection.recordId == record_id, Objection.objectorUid == user.uid,
        Objection.status == "待复核"))).scalar()
    if dup:
        raise HTTPException(400, "您对该记录已提交过异议，请等待复核结果")
    owner = await db.get(User, row.sid)
    title = record_title(e, serialize(row, e))
    obj = Objection(key=e.key, recordId=record_id, recordLabel=e.label, recordTitle=title,
                    sid=row.sid, objectorUid=user.uid, objectorName=user.name, reason=reason)
    db.add(obj)
    await log_op(db, user, "audit", f"对{e.label}《{title}》提出公示异议：{reason[:80]}",
                 key=e.key, label=e.label, record_id=record_id, sid=row.sid)
    for dean in await _dean_recipients(db, owner):
        await notify(db, uid=dean.uid, type="system",
                     title=f"收到公示异议：{e.label}《{title}》",
                     content=f"异议人 {user.name}（{user.uid}）。理由：{reason[:200]}。请及时在公示栏复核。",
                     key=e.key, record_id=record_id)
    await db.commit()
    bump()
    return {"code": 0, "data": {"id": obj.id}}


@router.get("/mine")
async def mine(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """我提出的异议及复核结果"""
    rows = (await db.execute(select(Objection).where(Objection.objectorUid == user.uid)
                             .order_by(Objection.createdAt.desc()).limit(100))).scalars().all()
    return {"code": 0, "data": {"list": [_obj_dict(o) for o in rows]}}


@router.get("")
async def list_objections(status: str = "待复核", page: int = Query(1, ge=1),
                          pageSize: int = Query(10, ge=1, le=100),
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """异议列表：院长全部可见，辅导员限名下学生（数据权限与审核一致）"""
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "仅辅导员/院长可查看异议列表")
    q = select(Objection, User).join(User, Objection.sid == User.id)
    if status and status != "全部":
        q = q.where(Objection.status == status)
    sids = await scope_sids(db, user)
    if sids is not None:
        q = q.where(Objection.sid.in_(sids))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(q.order_by(Objection.createdAt.desc())
                             .offset((page - 1) * pageSize).limit(pageSize))).all()
    lst = [{**_obj_dict(o), "owner": {"name": u.name, "classId": u.classId}} for o, u in rows]
    return {"code": 0, "data": {"list": lst, "total": total, "page": page, "pageSize": pageSize}}


@router.post("/{oid}/review")
async def review(oid: str, payload: dict, user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    """院长复核：成立 → 记录驳回撤销认定；不成立 → 维持认定（记录继续等公示期满自动生效）"""
    if user.role != "Dean":
        raise HTTPException(403, "仅院长可复核公示异议")
    obj = await db.get(Objection, oid)
    if obj is None:
        raise HTTPException(404, "异议不存在")
    if obj.status != "待复核":
        raise HTTPException(400, "该异议已复核，请勿重复操作")
    result = payload.get("result")
    opinion = str(payload.get("opinion") or "").strip()
    if result not in ("成立", "不成立"):
        raise HTTPException(400, "复核结论仅支持 成立 / 不成立")
    e = get_def(obj.key)
    row = await db.get(e.model, obj.recordId)
    obj.handledBy = user.name
    obj.handledTime = now().strftime("%Y-%m-%d %H:%M:%S")
    if result == "成立":
        if row is not None and row.status not in (STATUS_PUBLIC, "驳回"):
            raise HTTPException(400, f"该记录已「{row.status}」，异议成立无法撤销认定")
        if row is not None and row.status == STATUS_PUBLIC:
            stu = await db.get(User, row.sid)
            opinion_txt = f"公示异议成立：{obj.reason[:120]}"
            if opinion:
                opinion_txt += f"。复核意见：{opinion}"
            await _reject(db, e, obj.key, row, user, stu, opinion_txt, STATUS_PUBLIC)
        await log_op(db, user, "audit",
                     f"复核公示异议：{obj.recordLabel}《{obj.recordTitle}》异议成立，撤销认定",
                     key=obj.key, label=obj.recordLabel, record_id=obj.recordId, sid=obj.sid)
        await notify(db, uid=obj.objectorUid, type="system",
                     title="你提出的公示异议已复核：成立",
                     content=f"{obj.recordLabel}《{obj.recordTitle}》已撤销认定，感谢你的监督。",
                     key=obj.key, record_id=obj.recordId)
    else:
        await log_op(db, user, "audit",
                     f"复核公示异议：{obj.recordLabel}《{obj.recordTitle}》异议不成立，维持认定"
                     + (f"，意见：{opinion}" if opinion else ""),
                     key=obj.key, label=obj.recordLabel, record_id=obj.recordId, sid=obj.sid)
        await notify(db, uid=obj.objectorUid, type="system",
                     title="你提出的公示异议已复核：不成立",
                     content=(f"{obj.recordLabel}《{obj.recordTitle}》维持认定"
                              + (f"。复核意见：{opinion}" if opinion else "")
                              + "。记录将在公示期满后自动生效。"),
                     key=obj.key, record_id=obj.recordId)
    obj.status = result
    await db.commit()
    bump()
    return {"code": 0, "data": {"id": obj.id, "status": obj.status}}
