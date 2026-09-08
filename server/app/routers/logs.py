"""操作日志查询（合规留痕）

权限模型：
- Student：仅可看自己记录的日志（/logs/record/{key}/{id}，且记录须本人所有）
- Counsellor：名下学生相关日志
- Dean：全部日志
日志只增不删不改，不提供任何写接口（除内部 log_op）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import OperationLog, User, get_db
from app.security import get_current_user
from app.routers.entities import get_def

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _scoped(db: AsyncSession, user: User):
    """日志按记录归属学生做数据权限过滤"""
    q = select(OperationLog)
    if user.role == "Student":
        q = q.where(OperationLog.sid == user.id)
    elif user.role == "Counsellor":
        sids = select(User.id).where(User.counsellorId == user.id)
        q = q.where(OperationLog.sid.in_(sids))
    return q          # Dean 不加过滤


@router.get("")
async def list_logs(user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db),
                    action: str | None = None,
                    key: str | None = None,
                    keyword: str | None = None,
                    start: str | None = None,
                    end: str | None = None,
                    page: int = Query(1, ge=1),
                    pageSize: int = Query(15, ge=1, le=100)):
    """管理端日志检索（辅导员/院长）；学生走 /logs/record"""
    if user.role == "Student":
        raise HTTPException(403, "学生请通过记录详情查看操作记录")
    q = _scoped(db, user)
    if action:
        q = q.where(OperationLog.action == action)
    if key:
        q = q.where(OperationLog.entityKey == key)
    if keyword:
        kw = f"%{keyword}%"
        q = q.where(or_(OperationLog.summary.like(kw),
                        OperationLog.operatorName.like(kw),
                        OperationLog.uid.like(kw)))
    if start:   # createdAt 为 'YYYY-MM-DD HH:MM:SS' 字符串，字典序比较即可
        q = q.where(OperationLog.createdAt >= f"{start} 00:00:00")
    if end:
        q = q.where(OperationLog.createdAt <= f"{end} 23:59:59")
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(q.order_by(desc(OperationLog.createdAt))
                             .offset((page - 1) * pageSize).limit(pageSize))).scalars().all()
    data = [{"id": r.id, "uid": r.uid, "operatorName": r.operatorName, "role": r.role,
             "action": r.action, "entityKey": r.entityKey, "entityLabel": r.entityLabel,
             "recordId": r.recordId, "sid": r.sid, "summary": r.summary,
             "createdAt": r.createdAt} for r in rows]
    return {"code": 0, "data": {"list": data, "total": total, "page": page, "pageSize": pageSize}}


@router.get("/record/{key}/{record_id}")
async def record_logs(key: str, record_id: str,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """单条记录的完整操作时间线（学生本人/辅导员范围内/院长）"""
    get_def(key)  # 实体 key 合法性
    q = _scoped(db, user).where(OperationLog.entityKey == key,
                                OperationLog.recordId == record_id)
    rows = (await db.execute(q.order_by(OperationLog.createdAt))).scalars().all()
    return {"code": 0, "data": [
        {"action": r.action, "operatorName": r.operatorName, "role": r.role,
         "summary": r.summary, "createdAt": r.createdAt} for r in rows]}
