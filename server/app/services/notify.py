"""站内通知 — 消息本体入库（与业务同事务），邮件为可选异步触达渠道

设计要点：一份数据，多个渠道。notifications 表是唯一事实源，
邮件/SSE 只是"怎么让人知道有新消息"，删除渠道不影响消息中心。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, now
from app.services import mailer
from app.services.entity_registry import ENTITY_REGISTRY, category_scope
from app.services.oplog import record_title


def build(*, uid: str, title: str, content: str = "", type: str = "audit",
          key: str | None = None, record_id: str | None = None,
          is_read: bool = False):
    return {
        "uid": uid, "title": title, "content": content, "type": type,
        "linkKey": key, "linkId": record_id, "isRead": is_read,
    }


async def notify(db: AsyncSession, *, uid: str, title: str, content: str = "",
                 type: str = "audit", key: str | None = None,
                 record_id: str | None = None) -> None:
    """站内信入库（调用方负责与业务同事务 commit）"""
    from app.models.database import Notification
    db.add(Notification(**build(uid=uid, title=title, content=content,
                                type=type, key=key, record_id=record_id)))


_background_tasks: set = set()


def notify_by_mail(email: str | None, subject: str, content: str) -> None:
    """邮件旁路：业务 commit 后后台发送，失败仅记日志不影响事务。
    任务引用入集合防 GC（CPython 对无引用 task 可能中途回收），完成后自动清理"""
    if not email:
        return
    import asyncio
    task = asyncio.get_running_loop().create_task(mailer.send_async(email, subject, content))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def backfill_notifications(db: AsyncSession) -> int:
    """存量驳回记录合成站内通知（seed 用）：仅驳回（需要学生处理）；
    历史通知（>7 天）默认已读，近 7 天保持未读"""
    from datetime import timedelta

    from app.models.database import Notification

    cutoff = (now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for key, e in ENTITY_REGISTRY.items():
        q = select(e.model).where(e.model.status == "驳回")
        cat = category_scope(key, e.model)
        if cat is not None:
            q = q.where(cat)
        rows = (await db.execute(q)).scalars().all()
        if not rows:
            continue
        users = {u.id: u for u in (await db.execute(
            select(User).where(User.id.in_({r.sid for r in rows})))).scalars().all()}
        for r in rows:
            stu = users.get(r.sid)
            if stu is None:
                continue
            title = record_title(e, {f.name: getattr(r, f.name, None) for f in e.fields})
            db.add(Notification(**build(
                uid=stu.uid,
                title=f"你申报的{e.label}「{title}」被驳回",
                content=f"驳回原因：{r.opinion or '材料不符合要求'}。请按原因修改后重新提交。",
                key=key, record_id=r.id,
                is_read=(r.auditTime or "") < cutoff)))
            n += 1
    await db.commit()
    return n
