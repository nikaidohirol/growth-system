"""审核中心 — 多级审核流（辅导员初审 / 院长终审 / 公示期），注册表分发

状态机（见 services/audit_flow.py）：
    待审核 →(辅导员通过·日常类)→ 公示中 →(期满惰性)→ 通过
    待审核 →(辅导员通过·dean_review 类)→ 待院长审批 →(院长通过)→ 公示中
    任意非生效态 →(驳回·带原因)→ 驳回 →(学生修改重报)→ 待审核
    已生效/公示中记录仅院长可纠错（异议）驳回
Excel 补录「直接通过」为历史数据迁移通道，不走公示（见 entities.import_entities）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, get_db, now
from app.models.schemas import AuditSubmitReq
from app.security import get_current_user
from app.routers.entities import get_def, serialize
from app.services.audit_flow import (STATUS_DEAN, STATUS_PUBLIC,
                                     STATUS_REJECTED, publicity_end)
from app.services.credits import assess_inn_row
from app.services.entity_registry import ENTITY_REGISTRY, INN_CATEGORY, category_scope
from app.services.notify import notify, notify_by_mail
from app.services.oplog import log_op, record_title

router = APIRouter(prefix="/api/audit", tags=["audit"])


async def scope_sids(db: AsyncSession, user: User):
    """数据权限：辅导员只看自己名下学生，院长看全部"""
    if user.role == "Dean":
        return None
    return select(User.id).where(User.counsellorId == user.id)


async def _dean_recipients(db: AsyncSession, stu: User | None) -> list[User]:
    """审批通知收件院长：优先学生所属学院的院长，无学院归属时通知全部院长"""
    q = select(User).where(User.role == "Dean")
    if stu is not None and stu.college:
        scoped = q.where(User.college == stu.college)
        deans = (await db.execute(scoped)).scalars().all()
        if deans:
            return list(deans)
    return list((await db.execute(q)).scalars().all())


@router.get("/summary")
async def summary(user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """各实体待审核数量汇总（辅导员 dashboard / 审核中心 tab 角标）+ 待院长审批总数"""
    sids = await scope_sids(db, user)
    out, pending_total, dean_pending = [], 0, 0
    for key, e in ENTITY_REGISTRY.items():
        cat = category_scope(key, e.model)
        for status, acc in (("待审核", None), ("待院长审批", "dean")):
            q = select(func.count()).select_from(e.model).where(e.model.status == status)
            if cat is not None:
                q = q.where(cat)
            if sids is not None:
                q = q.where(e.model.sid.in_(sids))
            n = (await db.execute(q)).scalar() or 0
            if acc is None:
                pending_total += n
                if status == "待审核":
                    out.append({"key": key, "label": e.label, "group": e.group, "count": n})
            else:
                dean_pending += n
    approved = 0
    for key, e in ENTITY_REGISTRY.items():
        q = select(func.count()).select_from(e.model).where(e.model.status == "通过")
        cat = category_scope(key, e.model)
        if cat is not None:
            q = q.where(cat)
        if sids is not None:
            q = q.where(e.model.sid.in_(sids))
        approved += (await db.execute(q)).scalar() or 0
    return {"code": 0, "data": {"list": out, "pendingTotal": pending_total,
                                "approvedTotal": approved, "deanPendingTotal": dean_pending}}


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
    cat = category_scope(key, e.model)
    if cat is not None:
        q = q.where(cat)
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


def _guard_transition(user: User, old_status: str, result: str) -> None:
    """角色 × 状态机的操作权限矩阵"""
    if user.role not in ("Counsellor", "Dean"):
        raise HTTPException(403, "仅辅导员/院长可执行审核操作")
    if result not in ("通过", "驳回"):
        raise HTTPException(400, "审核结论仅支持 通过 / 驳回")
    if old_status == "通过" and result == "通过":
        raise HTTPException(400, "该记录已生效，无需重复审核")
    if old_status == STATUS_PUBLIC and result == "通过":
        raise HTTPException(400, "该记录公示中，公示期满自动生效")
    if user.role == "Counsellor":
        if old_status == STATUS_DEAN:
            raise HTTPException(400, "该记录已进入院长审批环节，辅导员不可再操作")
        if old_status in (STATUS_PUBLIC, "通过"):
            raise HTTPException(403, "公示中/已生效记录仅院长可纠错（异议）驳回")
        if old_status == "驳回":
            raise HTTPException(400, "该记录已被驳回，请等待学生修改后重新提交")


async def _enter_public(db: AsyncSession, e, key: str, row, user: User,
                        stu: User | None, opinion: str) -> tuple[str, str]:
    """终审通过 → 进入公示期：核定学分 + 留痕 + 通知学生（与业务同事务）"""
    row.status = STATUS_PUBLIC
    row.auditor = user.name
    row.opinion = opinion
    row.auditTime = now().strftime("%Y-%m-%d %H:%M:%S")
    row.publicEnd = publicity_end()
    # 审核通过 = 学分正式核定：按规则矩阵（INNOVATE_KV × 次序系数）服务端重算，不沿用自报值
    credit_note = ""
    if key in INN_CATEGORY:
        kv_field = next((f for f in e.fields if f.type == "kv"), None)
        credit = assess_inn_row(row, getattr(row, kv_field.name, None) if kv_field else None)
        if credit is not None:
            row.credit = credit
            credit_note = f"，核定学分 {credit:g}"
    title = record_title(e, serialize(row, e))
    stage = "终审通过" if user.role == "Dean" else "审核通过"
    await log_op(db, user, "audit",
                 f"{stage}{e.label}《{title}》，进入公示期（至 {row.publicEnd}）{credit_note}",
                 key=key, label=e.label, record_id=row.id, sid=row.sid)
    n_title = f"你申报的{e.label}「{title}」已通过{ '终审' if user.role == 'Dean' else '审核' }，进入公示期"
    n_content = (f"审核人 {user.name} {stage}你的申报{credit_note}。"
                 f"公示期至 {row.publicEnd}，期满自动生效；如对公示有异议请联系辅导员。")
    if stu is not None:
        await notify(db, uid=stu.uid, title=n_title, content=n_content, key=key, record_id=row.id)
    return n_title, n_content


async def _reject(db: AsyncSession, e, key: str, row, user: User,
                  stu: User | None, opinion: str, old_status: str) -> tuple[str, str]:
    """驳回（初审驳回 / 院长驳回 / 公示异议驳回 / 生效纠错驳回）：留痕 + 通知学生"""
    row.status = STATUS_REJECTED
    row.auditor = user.name
    row.opinion = opinion
    row.auditTime = now().strftime("%Y-%m-%d %H:%M:%S")
    row.publicEnd = None
    title = record_title(e, serialize(row, e))
    stage = {"待审核": "驳回", STATUS_PUBLIC: "公示异议驳回", "通过": "纠错驳回"}.get(old_status, "驳回")
    await log_op(db, user, "audit", f"{stage}{e.label}《{title}》，意见：{row.opinion}",
                 key=key, label=e.label, record_id=row.id, sid=row.sid)
    n_title = f"你申报的{e.label}「{title}」被驳回"
    n_content = f"{'公示期收到异议，' if old_status == STATUS_PUBLIC else ''}驳回原因：{row.opinion}。请按原因修改后重新提交。"
    if stu is not None:
        await notify(db, uid=stu.uid, title=n_title, content=n_content, key=key, record_id=row.id)
    return n_title, n_content


async def _submit_one(db: AsyncSession, e, key: str, row, user: User,
                      result: str, opinion: str) -> dict:
    """单条记录按状态机流转一步（submit 与 batch 共用），返回序列化结果"""
    old_status = row.status
    _guard_transition(user, old_status, result)
    stu = await db.get(User, row.sid)
    title = record_title(e, serialize(row, e))
    if result == "驳回":
        n_title, n_content = await _reject(db, e, key, row, user, stu, opinion, old_status)
    elif user.role == "Counsellor" and e.dean_review:
        # 初审通过 → 转院长终审（不核定学分，生效前核定）
        row.status = STATUS_DEAN
        row.auditor = user.name
        row.opinion = opinion or "初审通过"
        row.auditTime = now().strftime("%Y-%m-%d %H:%M:%S")
        await log_op(db, user, "audit",
                     f"初审通过{e.label}《{title}》，转院长审批，意见：{row.opinion}",
                     key=key, label=e.label, record_id=row.id, sid=row.sid)
        n_title = f"学生{stu.name if stu else ''}的{e.label}「{title}」待您院长审批" if stu else ""
        n_content = f"辅导员 {user.name} 初审通过，等待您终审。"
        if stu is not None:
            for dean in await _dean_recipients(db, stu):
                await notify(db, uid=dean.uid, type="system", title=n_title,
                             content=n_content, key=key, record_id=row.id)
    else:
        n_title, n_content = await _enter_public(
            db, e, key, row, user, stu, opinion or "材料齐全，同意认定")
    await db.commit()
    if stu is not None and n_title:
        notify_by_mail(stu.email, n_title, n_content)
    return serialize(row, e)


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
    data = await _submit_one(db, e, key, row, user, req.status, req.opinion or "")
    return {"code": 0, "data": data}


@router.post("/batch/{key}")
async def batch_confirm(key: str, payload: dict,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """院长批量确认：勾选多条「待院长审批」记录一键终审通过，逐条核定学分/进公示/留痕/通知"""
    if user.role != "Dean":
        raise HTTPException(403, "仅院长可批量确认")
    e = get_def(key)
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "未选择记录")
    rows = (await db.execute(
        select(e.model).where(e.model.id.in_(ids), e.model.status == STATUS_DEAN))).scalars().all()
    confirmed = 0
    for row in rows:
        await _submit_one(db, e, key, row, user, "通过", "批量确认无误，同意认定")
        confirmed += 1
    return {"code": 0, "data": {"confirmed": confirmed, "skipped": len(ids) - confirmed}}
