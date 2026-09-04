"""通用实体 CRUD — 由实体注册表驱动，13 类业务页面共用这一套路由"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import INNOVATE_KV
from app.models.database import Innovation, User, get_db
from app.security import get_current_user
from app.services.entity_registry import ENTITY_REGISTRY, INN_CATEGORY

router = APIRouter(prefix="/api/entities", tags=["entities"])


def get_def(key: str):
    e = ENTITY_REGISTRY.get(key)
    if e is None:
        raise HTTPException(404, f"未知实体类型：{key}")
    return e


def serialize(row: Any, e) -> dict:
    data = {"id": row.id, "status": row.status, "auditor": row.auditor,
            "opinion": row.opinion, "auditTime": row.auditTime,
            "files": row.files or [], "createdAt": row.createdAt}
    for f in e.fields:
        data[f.name] = getattr(row, f.name, None)
    return data


def apply_kv(e, payload: dict, data: dict) -> str | None:
    """kv 字段：两级选择（chiefly·minor）落库展示值 + 按规则自动计算学分"""
    kv_field = next((f for f in e.fields if f.type == "kv"), None)
    if kv_field is None:
        return None
    chiefly, minor = payload.get("_kv_chiefly"), payload.get("_kv_minor")
    if not chiefly or not minor:
        return "请选择完整的学分认定项"
    category = kv_field.kv_category
    credit = INNOVATE_KV.get(category, {}).get("kv", {}).get(chiefly, {}).get(minor)
    if credit is None:
        return f"无效的认定组合：{chiefly} / {minor}"
    data[kv_field.name] = f"{chiefly}·{minor}"
    data["credit"] = float(credit)
    return None


async def owned_row(db: AsyncSession, e, key: str, row_id: str, user: User):
    row = await db.get(e.model, row_id)
    if row is None or (user.role == "Student" and row.sid != user.id):
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
    data, errors = e.validate_payload(payload)
    err = apply_kv(e, payload, data)
    if errors or err:
        raise HTTPException(400, "；".join(errors + ([err] if err else [])))
    if key in INN_CATEGORY:
        data["category"] = INN_CATEGORY[key]
    data["sid"] = user.id
    row = e.model(id=uuid.uuid4().hex, **data)
    db.add(row)
    await db.commit()
    return {"code": 0, "data": serialize(row, e)}


@router.put("/{key}/{row_id}")
async def update_entity(key: str, row_id: str, payload: dict,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await owned_row(db, e, key, row_id, user)
    if row.status == "通过":
        raise HTTPException(400, "已通过的记录不可修改")
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
    await db.commit()
    return {"code": 0, "data": serialize(row, e)}


@router.delete("/{key}/{row_id}")
async def delete_entity(key: str, row_id: str,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    e = get_def(key)
    row = await owned_row(db, e, key, row_id, user)
    if row.status == "通过":
        raise HTTPException(400, "已通过的记录不可删除")
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
