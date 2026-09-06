"""多级审核流 — 分级审批 + 公示期 + 申报窗口

设计要点：
- 状态机：待审核 →(辅导员通过·院长终审类 dean_review=True)→ 待院长审批 →(院长通过)→ 公示中
                                                                       └→(公示异议)→ 驳回
          待审核 →(辅导员通过·日常类)→ 公示中 →(期满)→ 通过；任意非生效态可驳回
- 「通过」恒等于已生效：学分统计/看板等存量 status=='通过' 查询语义自动正确，无需改动
- 公示期满转「通过」用惰性晋升（promote_expired 挂在 get_db，每次请求顺带一条 UPDATE），
  不引入后台调度器；读时计算保证全系统状态一致
- 公示监督闭环：公示中记录可被实名异议，挂着「待复核」异议的记录暂停惰性晋升，待院长复核后流转
- 学分正式核定在「进入公示」时执行；Excel 补录「直接通过」为历史数据迁移通道，不走公示
- 申报窗口仅约束学生自主申报（create/update）；辅导员/院长的补录与审核不受窗口限制
"""
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import AUDIT_FLOW
from app.models.database import Objection, now
from app.services.entity_registry import ENTITY_REGISTRY

STATUS_PENDING = "待审核"
STATUS_DEAN = "待院长审批"
STATUS_PUBLIC = "公示中"
STATUS_PASSED = "通过"
STATUS_REJECTED = "驳回"

# 学生可修改/删除的状态（待院长审批/公示中/已生效均锁定）
EDITABLE_STATUSES = (STATUS_PENDING, STATUS_REJECTED)


def publicity_end() -> str:
    """公示截止时间 = 当前时间 + 公示期天数"""
    return (now() + timedelta(days=int(AUDIT_FLOW["publicityDays"]))).strftime("%Y-%m-%d %H:%M:%S")


def window_error() -> str | None:
    """学生自主申报窗口校验：窗口外返回提示文案，窗口内返回 None"""
    today = now().strftime("%Y-%m-%d")
    if not (str(AUDIT_FLOW["windowStart"]) <= today <= str(AUDIT_FLOW["windowEnd"])):
        return (f"当前不在本学期申报窗口内（{AUDIT_FLOW['windowStart']} ~ {AUDIT_FLOW['windowEnd']}），"
                "请等待窗口开放，或联系辅导员进行历史数据补录")
    return None


async def promote_expired(db: AsyncSession) -> int:
    """公示期满惰性晋升：公示中且公示期已过 → 正式生效（通过）

    挂载在 get_db 依赖上每次请求顺带执行；单条 UPDATE/表，status 有索引，微秒级。
    挂着「待复核」公示异议的记录排除在外——有人异议就先别生效，复核后再流转。
    """
    t = now().strftime("%Y-%m-%d %H:%M:%S")
    total = 0
    pending = select(Objection.recordId).where(Objection.status == "待复核")
    models = list(dict.fromkeys(e.model for e in ENTITY_REGISTRY.values()))
    for m in models:
        res = await db.execute(
            update(m).where(m.status == STATUS_PUBLIC, m.publicEnd <= t,
                            m.id.not_in(pending))
            .values(status=STATUS_PASSED))
        total += res.rowcount or 0
    if total:
        await db.commit()
    return total
