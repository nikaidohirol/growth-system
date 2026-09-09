"""业务字典与实体契约"""
from functools import lru_cache

from fastapi import APIRouter

from app.meta import META_ALL
from app.services.entity_registry import registry_payload

router = APIRouter(prefix="/api/meta", tags=["meta"])


@lru_cache(maxsize=1)
def _entities_contract():
    """注册表契约进程内只算一次（纯静态数据，随代码部署变更）"""
    return registry_payload()


@router.get("/all")
async def all_meta():
    return {"code": 0, "data": META_ALL}


@router.get("/entities")
async def entities_contract():
    """实体注册表契约 — 前端泛型 EntityPage 依据此渲染"""
    return {"code": 0, "data": _entities_contract()}
