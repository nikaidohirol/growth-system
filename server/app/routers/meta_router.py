"""业务字典与实体契约"""
from fastapi import APIRouter

from app.meta import META_ALL
from app.services.entity_registry import registry_payload

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/all")
async def all_meta():
    return {"code": 0, "data": META_ALL}


@router.get("/entities")
async def entities_contract():
    """实体注册表契约 — 前端泛型 EntityPage 依据此渲染"""
    return {"code": 0, "data": registry_payload()}
