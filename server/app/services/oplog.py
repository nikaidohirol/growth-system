"""操作日志服务 — 实体增删改 / 审核 / 登录统一留痕

设计要点：
- log_op 只构造并挂载到当前会话，随业务操作同事务提交（业务回滚日志一并回滚，不产生孤儿日志）
- update 用字段级 diff 生成人读摘要；kv 字段展示值统一 '·' → ' / '
- backfill_oplogs 供 seed / 一次性脚本使用：为存量记录合成「申报 + 审核」两条日志
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, gen_id, now
from app.services.entity_registry import EntityDef


def _fmt(v) -> str:
    if v is None or v == "":
        return "空"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).replace("·", " / ")[:40]


def build_log(uid: str, operator_name: str, role: str, action: str, summary: str, *,
              key: str | None = None, label: str | None = None,
              record_id: str | None = None, sid: str | None = None,
              created_at: str | None = None):
    """构造一条 OperationLog（字典形态，供 ORM 挂载或 bulk 插入）"""
    from app.models.database import OperationLog
    return OperationLog(
        id=gen_id(), uid=uid, operatorName=operator_name, role=role, action=action,
        entityKey=key, entityLabel=label, recordId=record_id, sid=sid, summary=summary[:500],
        createdAt=created_at or now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def diff_summary(e: EntityDef, old: dict, new: dict) -> str:
    """实体更新前后字段级 diff（跳过未变化字段），返回人读摘要"""
    parts = []
    for f in e.fields:
        o, n = old.get(f.name), new.get(f.name)
        if o == n:
            continue
        if isinstance(o, float) and isinstance(n, float) and abs(o - n) < 1e-9:
            continue
        parts.append(f"{f.label}: {_fmt(o)} → {_fmt(n)}")
    return "；".join(parts) if parts else "无字段变化"


def record_title(e: EntityDef, data: dict) -> str:
    """取记录的业务主标题：优先名称类字段，其次 kv 展示值"""
    title_field = next((f for f in e.fields if f.name in
                        ("project", "name", "team", "title", "honor")), e.fields[0])
    v = data.get(title_field.name)
    return _fmt(v) if v else e.label


async def log_op(db: AsyncSession, user: User, action: str, summary: str, *,
                 key: str | None = None, label: str | None = None,
                 record_id: str | None = None, sid: str | None = None) -> None:
    """在当前会话挂载一条操作日志（与业务同事务提交）"""
    db.add(build_log(user.uid, user.name, user.role, action, summary,
                     key=key, label=label, record_id=record_id, sid=sid))


async def backfill_oplogs(db: AsyncSession) -> int:
    """为存量记录合成操作日志：每条记录一条「申报」，已审核的再补一条「审核」。

    返回写入条数。仅用于 seed 与一次性数据修复，运行时不调用。
    """
    from app.models.database import OperationLog
    from app.routers.entities import serialize
    from app.services.entity_registry import ENTITY_REGISTRY, category_scope

    users = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    exist = (await db.execute(select(OperationLog.recordId))).scalars().all()
    has_log = {r for r in exist if r}
    logs = []
    for key, e in ENTITY_REGISTRY.items():
        q = select(e.model)
        cat = category_scope(key, e.model)   # inn 7 类共用一张表，必须按 key 对应类别过滤
        if cat is not None:
            q = q.where(cat)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            if r.id in has_log:
                continue
            stu = users.get(r.sid)
            data = serialize(r, e)
            title = record_title(e, data)
            logs.append(build_log(stu.uid if stu else "", stu.name if stu else r.sid or "",
                                  "Student", "create",
                                  f"申报{e.label}《{title}》",
                                  key=key, label=e.label, record_id=r.id,
                                  sid=r.sid, created_at=r.createdAt))
            if r.status != "待审核":
                # 审核人反查 uid（按姓名，种子辅导员姓名唯一）
                op = next((u for u in users.values() if u.name == r.auditor), None)
                credit = getattr(r, "credit", None)
                stage = {"通过": "审核通过", "驳回": "审核驳回",
                         "待院长审批": "初审通过（转院长审批）",
                         "公示中": "终审通过（进入公示期）"}.get(r.status, f"审核{r.status}")
                logs.append(build_log(op.uid if op else "", r.auditor or "",
                                      op.role if op else "Counsellor", "audit",
                                      f"{stage}{e.label}《{title}》"
                                      f"{'，核定学分 ' + _fmt(credit) if credit is not None else ''}"
                                      f"{'，意见：' + r.opinion if r.opinion and r.opinion != r.status else ''}",
                                      key=key, label=e.label, record_id=r.id,
                                      sid=r.sid, created_at=r.auditTime))
    db.add_all(logs)
    await db.commit()
    return len(logs)
