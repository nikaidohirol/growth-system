"""学分计算共享服务 — dashboard / Agent 工具 / 学生管理共用同一口径"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import CREDIT_RULES, INNOVATE_KV
from app.models.database import Innovation, Voluntary
from app.models.database import Practice as PracticeModel


async def compute_pandect(db: AsyncSession, sid: str) -> dict:
    rows = (await db.execute(select(Innovation).where(Innovation.sid == sid))).scalars().all()
    inn_list = []
    for cat, conf in INNOVATE_KV.items():
        credit = sum(r.credit or 0 for r in rows if r.category == cat and r.status == "通过")
        inn_list.append({"key": conf["label"], "value": round(credit, 2)})
    inn_credit = round(sum(x["value"] for x in inn_list), 2)

    pra_count = len((await db.execute(select(PracticeModel.id).where(
        PracticeModel.sid == sid, PracticeModel.status == "通过"))).all())
    vol_hours = 0.0
    for v in (await db.execute(select(Voluntary.duration).where(
            Voluntary.sid == sid, Voluntary.status == "通过"))).scalars():
        vol_hours += v or 0

    r = CREDIT_RULES
    pra_credit = min(pra_count * r["practice_credit"], r["practice_cap"])
    vol_credit = min(int(vol_hours // r["voluntary_hours_per_credit"]) * r["voluntary_credit"],
                     r["voluntary_cap"])
    pra_total = round(pra_credit + vol_credit, 2)

    return {
        "innCredit": inn_credit, "praCredit": pra_total,
        "sumCredit": round(inn_credit + pra_total, 2),
        "innCreditList": inn_list,
        "practiceCreditList": [{"key": "社会实践", "value": round(pra_credit, 2)},
                               {"key": "志愿服务", "value": round(vol_credit, 2)}],
        "rules": CREDIT_RULES,
        "practiceCount": pra_count, "voluntaryHours": round(vol_hours, 1),
    }
