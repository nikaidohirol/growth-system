"""学分计算共享服务 — dashboard / Agent 工具 / 学生管理共用同一口径"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import CREDIT_RULES, INNOVATE_KV
from app.models.database import Innovation, Voluntary
from app.models.database import Practice as PracticeModel


def assess_inn_credit(category: str, chiefly: str, minor: str,
                      post: str | None = None) -> float | None:
    """按规则矩阵核定创新学分类学分：基准分(INNOVATE_KV) × 人员次序系数(如配置)。

    返回 None 表示认定组合无效（矩阵中不存在）。
    """
    conf = INNOVATE_KV.get(category)
    if not conf:
        return None
    base = conf.get("kv", {}).get(chiefly, {}).get(minor)
    if base is None:
        return None
    factor = 1.0
    pf = conf.get("post_factor")
    if pf and post:
        factor = pf.get(post)
        if factor is None:  # 关键词兜底（如"第二完成人(团队)"类变体）
            factor = next((f for kw, f in pf.items() if kw[:2] and kw[:2] in post), 1.0)
    return round(float(base) * float(factor), 2)


def assess_inn_row(row: Innovation, kv_field_value: str | None) -> float | None:
    """从已落库记录反推核定学分：解析 kv 存量值（兼容 '·' 与 ' / ' 两种分隔）+ post。"""
    if not kv_field_value:
        return None
    parts = [p.strip() for p in kv_field_value.replace("／", "/").split("·", 1)]
    if len(parts) != 2:
        parts = [p.strip() for p in kv_field_value.split("/", 1)]
    if len(parts) != 2 and row.category == "chair" and row.implementation:
        # 讲座类种子数据形态：project=讲座系列(chiefly)，implementation="场次·主题"
        parts = [kv_field_value.strip(), row.implementation.split("·", 1)[0].strip()]
    if len(parts) != 2:
        return None
    return assess_inn_credit(row.category, parts[0], parts[1], row.post)


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
