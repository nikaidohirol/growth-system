"""通用实体 CRUD — 由实体注册表驱动，13 类业务页面共用这一套路由"""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import AWARD_POST, HONOR_LEVEL, ORGAN_CASCADER, PARTY_TYPE, PRACTICE_TYPE
from app.models.database import User, get_db, now
from app.security import get_current_user
from app.services.audit_flow import EDITABLE_STATUSES, window_error
from app.services.credits import assess_inn_credit
from app.services.entity_registry import ENTITY_REGISTRY, INN_CATEGORY
from app.services.notify import notify
from app.services.oplog import _fmt, diff_summary, log_op, record_title

router = APIRouter(prefix="/api/entities", tags=["entities"])


def get_def(key: str):
    e = ENTITY_REGISTRY.get(key)
    if e is None:
        raise HTTPException(404, f"未知实体类型：{key}")
    return e


def serialize(row: Any, e) -> dict:
    data = {"id": row.id, "status": row.status, "auditor": row.auditor,
            "opinion": row.opinion, "auditTime": row.auditTime,
            "publicEnd": getattr(row, "publicEnd", None),
            "files": row.files or [], "createdAt": row.createdAt,
            "credit": getattr(row, "credit", None)}
    for f in e.fields:
        data[f.name] = getattr(row, f.name, None)
    return data


def apply_kv(e, payload: dict, data: dict) -> str | None:
    """kv 字段：两级选择（chiefly·minor）落库展示值 + 服务端按规则矩阵核定学分"""
    kv_field = next((f for f in e.fields if f.type == "kv"), None)
    if kv_field is None:
        return None
    chiefly, minor = payload.get("_kv_chiefly"), payload.get("_kv_minor")
    if not chiefly or not minor:
        return "请选择完整的学分认定项"
    category = kv_field.kv_category
    # 服务端核定（基准分 × 人员次序系数），不信任客户端传值
    credit = assess_inn_credit(category, chiefly, minor, payload.get("post"))
    if credit is None:
        return f"无效的认定组合：{chiefly} / {minor}"
    data[kv_field.name] = f"{chiefly}·{minor}"
    data["credit"] = credit
    return None


async def owned_row(db: AsyncSession, e, key: str, row_id: str, user: User):
    row = await db.get(e.model, row_id)
    # Innovation 7 类共用一张表：实体 key 与记录 category 不符视同不存在
    if row is None or (user.role == "Student" and row.sid != user.id) \
            or (key in INN_CATEGORY and row.category != INN_CATEGORY[key]):
        raise HTTPException(404, "记录不存在")
    return row


@router.get("/{key}")
async def list_entities(
    key: str,
    page: int = Query(1, ge=1), pageSize: int = Query(10, ge=1, le=100),
    keyword: str = "", sid: str = "", status: str = "",
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    e = get_def(key)
    q = select(e.model)
    # Innovation 7 类共用一张表，按实体 key 对应的 category 过滤
    if key in INN_CATEGORY:
        q = q.where(e.model.category == INN_CATEGORY[key])
    if user.role == "Student":
        q = q.where(e.model.sid == user.id)
    elif sid:
        q = q.where(e.model.sid == sid)
    elif user.role == "Counsellor":
        subs = select(User.id).where(User.counsellorId == user.id)
        q = q.where(e.model.sid.in_(subs))
    if keyword:
        conds = [cast(getattr(e.model, f), String).like(f"%{keyword}%") for f in e.search_fields]
        q = q.where(or_(*conds))
    if status:
        q = q.where(e.model.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.order_by(e.model.createdAt.desc()).offset((page - 1) * pageSize).limit(pageSize)
    )).scalars().all()
    return {"code": 0, "data": {"list": [serialize(r, e) for r in rows],
                                "total": total, "page": page, "pageSize": pageSize}}


@router.post("/{key}")
async def create_entity(key: str, payload: dict,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if user.role != "Student":
        raise HTTPException(403, "仅学生可提交申请")
    e = get_def(key)
    err_w = window_error()               # 申报窗口：学生自主申报仅限窗口期内（辅导员/院长补录不受限）
    if err_w:
        raise HTTPException(400, err_w)
    data, errors = e.validate_payload(payload)
    err = apply_kv(e, payload, data)
    if errors or err:
        raise HTTPException(400, "；".join(errors + ([err] if err else [])))
    if key in INN_CATEGORY:
        data["category"] = INN_CATEGORY[key]
    data["sid"] = user.id
    row = e.model(id=uuid.uuid4().hex, **data)
    db.add(row)
    await db.flush()
    await log_op(db, user, "create", f"申报{e.label}《{record_title(e, data)}》"
                                     f"{'，核定学分 ' + _fmt(data['credit']) if 'credit' in data else ''}",
                 key=key, label=e.label, record_id=row.id, sid=user.id)
    await db.commit()
    return {"code": 0, "data": serialize(row, e)}


@router.put("/{key}/{row_id}")
async def update_entity(key: str, row_id: str, payload: dict,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await owned_row(db, e, key, row_id, user)
    if row.status not in EDITABLE_STATUSES:   # 待院长审批/公示中/已生效均锁定
        raise HTTPException(400, "当前状态不可修改（审核中/公示中/已生效记录已锁定，如有异议请联系辅导员）")
    old = serialize(row, e)
    data, errors = e.validate_payload(payload)
    err = apply_kv(e, payload, data)
    if errors or err:
        raise HTTPException(400, "；".join(errors + ([err] if err else [])))
    if "files" in payload:
        row.files = payload.get("files") or []
    for k, v in data.items():
        setattr(row, k, v)
    row.status = "待审核"          # 驳回后重新提交自动回到待审核
    row.auditor = row.opinion = row.auditTime = None
    diff = diff_summary(e, old, serialize(row, e))
    await log_op(db, user, "update", f"修改{e.label}《{record_title(e, old)}》：{diff}",
                 key=key, label=e.label, record_id=row.id, sid=row.sid)
    # 驳回后重新提交：通知辅导员复审，形成审核闭环
    if old["status"] == "驳回" and user.counsellorId:
        couns = await db.get(User, user.counsellorId)
        if couns is not None:
            await notify(db, uid=couns.uid, type="system",
                         title=f"学生 {user.name} 重新提交了{e.label}申报",
                         content=f"「{record_title(e, serialize(row, e))}」此前被驳回，已按原因修改并重新提交，请及时复审。",
                         key=key, record_id=row.id)
    await db.commit()
    return {"code": 0, "data": serialize(row, e)}


@router.delete("/{key}/{row_id}")
async def delete_entity(key: str, row_id: str,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await owned_row(db, e, key, row_id, user)
    if row.status not in EDITABLE_STATUSES:
        raise HTTPException(400, "当前状态不可删除（审核中/公示中/已生效记录已锁定，如有异议请联系辅导员）")
    old = serialize(row, e)
    await log_op(db, user, "delete", f"删除{e.label}《{record_title(e, old)}》"
                                     f"{'，核定学分 ' + _fmt(row.credit) if getattr(row, 'credit', None) is not None else ''}",
                 key=key, label=e.label, record_id=row.id, sid=row.sid)
    await db.delete(row)
    await db.commit()
    return {"code": 0}


@router.get("/{key}/{row_id}")
async def get_entity(key: str, row_id: str,
                     user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await owned_row(db, e, key, row_id, user)
    return {"code": 0, "data": serialize(row, e)}


# ---- Excel 批量导入 ----
_SELECT_DICTS = {
    "honor_level": HONOR_LEVEL, "practice_type": PRACTICE_TYPE,
    "party_type": PARTY_TYPE, "award_post": AWARD_POST,
}


def _norm_date(v: Any) -> str:
    """Excel 日期轻量归一：2024/5/1、2024.5.1、2024年5月1日 → 2024-05-01，无法解析原样返回"""
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _validate_options(e, data: dict) -> list[str]:
    """导入防呆：select/cascader 取值必须命中业务字典（表单端由控件限制，Excel 端文本无法限制）"""
    errors = []
    for f in e.fields:
        v = data.get(f.name)
        if v is None:
            continue
        if f.type == "select" and f.options in _SELECT_DICTS and v not in _SELECT_DICTS[f.options]:
            errors.append(f"{f.label}「{v}」不在可选值内（{(' / '.join(_SELECT_DICTS[f.options]))}）")
        if f.type == "cascader" and v not in ORGAN_CASCADER:
            errors.append(f"{f.label}「{v}」不在可选值内（{(' / '.join(ORGAN_CASCADER))}）")
    post, org = data.get("post"), data.get("type")
    if org in ORGAN_CASCADER and post and post not in ORGAN_CASCADER[org]:
        errors.append(f"担任职务「{post}」与组织类型不匹配（可选：{' / '.join(ORGAN_CASCADER[org])}）")
    return errors


@router.post("/{key}/import")
async def import_entities(key: str, payload: dict,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Excel 批量导入（前端 xlsx 解析后按字段名提交行数组，服务端逐行校验 + 核定学分 + 留痕）

    - Student：仅导入本人记录，状态固定「待审核」
    - Counsellor/Dean：行内须带 sid（学号）指定归属学生，status 可选「通过」直接认定（历史数据迁移）
    """
    e = get_def(key)
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "没有可导入的数据")
    want_status = payload.get("status") or "待审核"
    if want_status not in ("待审核", "通过"):
        raise HTTPException(400, "status 仅支持 待审核 / 通过")
    if user.role == "Student":
        want_status = "待审核"

    # 批量解析行内学号 → 学生（辅导员/院长补录历史数据）
    uid_map: dict[str, User] = {}
    if user.role != "Student":
        uids = list({str(r.get("sid") or "").strip() for r in rows if r.get("sid")})
        if uids:
            found = (await db.execute(
                select(User).where(User.uid.in_(uids), User.role == "Student"))).scalars().all()
            uid_map = {u.uid: u for u in found}

    created, errors = 0, []
    for i, raw in enumerate(rows, start=1):
        try:
            row_payload = {k: v for k, v in raw.items() if v is not None}
            sid = user.id
            if user.role != "Student":
                stu = uid_map.get(str(row_payload.get("sid") or "").strip())
                if stu is None:
                    errors.append({"row": i, "message": "学号为空或不存在"})
                    continue
                if user.role == "Counsellor" and stu.counsellorId != user.id:
                    errors.append({"row": i, "message": f"{stu.uid} 不在您的管理范围内"})
                    continue
                sid = stu.id
            for f in e.fields:                     # Excel 日期归一
                if f.type == "date" and row_payload.get(f.name) is not None:
                    row_payload[f.name] = _norm_date(row_payload[f.name])
            data, errs = e.validate_payload(row_payload)
            err = apply_kv(e, row_payload, data)   # kv 组合校验 + 服务端核定学分
            errs += _validate_options(e, data)
            if errs or err:
                errors.append({"row": i, "message": "；".join(errs + ([err] if err else []))})
                continue
            if key in INN_CATEGORY:
                data["category"] = INN_CATEGORY[key]
            data["sid"] = sid
            data["status"] = want_status
            if want_status == "通过":
                data["auditor"] = user.name
                data["opinion"] = "历史数据批量导入"
                data["auditTime"] = now().strftime("%Y-%m-%d %H:%M:%S")
            row = e.model(id=uuid.uuid4().hex, **data)
            db.add(row)
            await db.flush()
            await log_op(db, user, "create", f"批量导入{e.label}《{record_title(e, data)}》"
                                             f"{'，核定学分 ' + _fmt(data['credit']) if 'credit' in data else ''}"
                                             f"{'，状态 ' + want_status if user.role != 'Student' else ''}",
                         key=key, label=e.label, record_id=row.id, sid=sid)
            created += 1
        except Exception as exc:                    # 单行异常不阻断整批
            errors.append({"row": i, "message": f"数据格式错误：{exc}"})
    await db.commit()
    return {"code": 0, "data": {"created": created, "errors": errors}}
