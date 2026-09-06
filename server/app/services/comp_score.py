"""综测过程分测算引擎 — 只统计已生效（status=='通过'）记录，读时计算不落库

定位：系统测算 ≠ 替代教务综测。GpaComp 导入的 comp/compRank 是学院线下评定后报教务的
权威结果；本引擎用系统内已生效记录实时测算过程分与专业内排名，两者并存对照。
- 与审核流状态机咬合：「通过」恒等于已生效 → 待审核/公示中/驳回记录自动不参与测算
- 读时计算：按学生范围数条聚合查询（sid 均有索引），毫秒级；无后台任务
- 排名口径：同年级同专业（评奖/保研的天然口径），非班级
- 加分明细逐条可追溯（实体 key + recordId + 来源标签 + 加分值），规则全在 meta.COMPREHENSIVE_RULE
"""
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta import COMPREHENSIVE_RULE, INNOVATE_KV
from app.models.database import (GpaComp, Honor, Innovation, Organization,
                                 Party, Practice, User, Voluntary)

MORAL, SPORTS = COMPREHENSIVE_RULE["moral"], COMPREHENSIVE_RULE["sports"]

# Innovation category -> 实体 key（明细追溯跳转用）
CAT_KEY = {v: k for k, v in
           {"inn_chair": "chair", "inn_project": "project", "inn_competition": "competition",
            "inn_enterprise": "enterprise", "inn_paper": "paper", "inn_patent": "patent",
            "inn_other": "other"}.items()}


def _is_sports_honor(project: str) -> bool:
    """荣誉是否文体类：按名称关键词归类（真实学院综测细则的通行做法）"""
    return any(kw in (project or "") for kw in SPORTS["honorKeywords"])


def _cadre_score(post: str) -> float:
    """学生干部加分：按职务关键词匹配取最高，不逐岗叠加"""
    scores = [v for kw, v in MORAL["cadre"].items() if kw in (post or "")]
    return max(scores) if scores else 0.0


async def forecast(db: AsyncSession, sid_q=None) -> list[dict]:
    """测算给定学生范围（sid 子查询，None=全部学生）的综测过程分，按专业内排名

    排名口径恒为「目标学生所在年级×专业的完整名单」（评奖/保研的天然口径，非班级）——
    学生查本人时也按同年级同专业全员计算排名，而非仅本人；返回仅含目标学生。
    返回字段：学业（最近学期 GPA 换算）/ 德育 / 文体（基准分+可追溯明细）/ 创新加分 /
    测算总分 / 专业内排名，并与教务导入的综测成绩排名并列展示
    """
    targets = (await db.execute(
        select(User).where(User.role == "Student",
                           User.id.in_(sid_q) if sid_q is not None else true())
        .order_by(User.periods, User.major, User.uid))).scalars().all()
    if not targets:
        return []
    users = list(targets)
    if sid_q is not None:
        # 补齐同年级同专业全部学生，保证排名口径完整
        groups = sorted({(u.periods, u.major) for u in targets if u.major})
        if groups:
            have = {u.id for u in users}
            extra = (await db.execute(select(User).where(
                User.role == "Student",
                or_(*(and_(User.periods == p, User.major == m) for p, m in groups))))).scalars().all()
            for u in extra:
                if u.id not in have:
                    users.append(u)
    ids = [u.id for u in users]

    # 最近一学期 GPA + 教务导入综测（并存对照的「权威结果」）
    latest: dict[str, dict] = {}
    for sid, sem, gpa, comp, rank, max_rank in (await db.execute(
            select(GpaComp.sid, GpaComp.semester, GpaComp.gpa, GpaComp.comp,
                   GpaComp.compRank, GpaComp.maxRank)
            .where(GpaComp.sid.in_(ids)).order_by(GpaComp.semester))).all():
        if sid not in latest or sem >= latest[sid]["semester"]:
            latest[sid] = {"semester": sem, "gpa": gpa, "comp": comp,
                           "compRank": rank, "maxRank": max_rank}

    # 已生效记录明细（仅 status=='通过'：待审核/公示中/驳回一律不参与测算）
    vol = (await db.execute(select(Voluntary.sid, Voluntary.id, Voluntary.project,
                                   Voluntary.duration)
                            .where(Voluntary.status == "通过", Voluntary.sid.in_(ids)))).all()
    pra = (await db.execute(select(Practice.sid, Practice.id, Practice.team)
                            .where(Practice.status == "通过", Practice.sid.in_(ids)))).all()
    par = (await db.execute(select(Party.sid, Party.id, Party.type)
                            .where(Party.status == "通过", Party.sid.in_(ids)))).all()
    hon = (await db.execute(select(Honor.sid, Honor.id, Honor.project, Honor.level)
                            .where(Honor.status == "通过", Honor.sid.in_(ids)))).all()
    org = (await db.execute(select(Organization.sid, Organization.id, Organization.post)
                            .where(Organization.status == "通过", Organization.sid.in_(ids)))).all()
    inn = (await db.execute(select(Innovation.sid, Innovation.id, Innovation.category,
                                   Innovation.project, Innovation.credit)
                            .where(Innovation.status == "通过", Innovation.sid.in_(ids)))).all()

    acc: dict[str, dict] = {u.id: {"volHours": 0.0, "volItem": None, "party": None,
                                   "cadre": None, "moralHonors": [], "sportsHonors": [],
                                   "praIds": [], "innItems": []} for u in users}
    for sid, rid, proj, dur in vol:
        a = acc[sid]
        a["volHours"] += dur or 0
        a["volItem"] = (rid, proj)
    for sid, rid, typ in par:
        s = MORAL["party"].get(typ, 0)
        if s and (acc[sid]["party"] is None or s > acc[sid]["party"][2]):
            acc[sid]["party"] = (rid, typ, s)
    for sid, rid, post in org:
        s = _cadre_score(post)
        if s and (acc[sid]["cadre"] is None or s > acc[sid]["cadre"][2]):
            acc[sid]["cadre"] = (rid, post, s)
    for sid, rid, proj, level in hon:
        tgt = acc[sid]["sportsHonors"] if _is_sports_honor(proj) else acc[sid]["moralHonors"]
        tgt.append((rid, proj, level, (SPORTS if tgt is acc[sid]["sportsHonors"] else MORAL)["honor"].get(level, 0)))
    for sid, rid, team in pra:
        acc[sid]["praIds"].append((rid, team))
    for sid, rid, cat, proj, credit in inn:
        if credit:
            acc[sid]["innItems"].append((rid, cat, proj, float(credit)))

    out = []
    for u in users:
        a = acc[u.id]
        g = latest.get(u.id)
        academic = round(g["gpa"] * COMPREHENSIVE_RULE["academic"]["gpaToScore"], 2) if g else 0.0
        moral, moral_items = MORAL["base"], []
        sports, sports_items = SPORTS["base"], []

        v = min(a["volHours"] / MORAL["voluntary"]["perHours"] * MORAL["voluntary"]["credit"],
                MORAL["voluntary"]["cap"])
        if v > 0:
            moral += v
            rid, proj = a["volItem"]
            moral_items.append({"key": "voluntary", "recordId": rid,
                                "label": f"志愿服务 {a['volHours']:g}h", "score": round(v, 2)})
        if a["party"]:
            rid, typ, s = a["party"]
            moral += s
            moral_items.append({"key": "party", "recordId": rid, "label": typ, "score": s})
        if a["cadre"]:
            rid, post, s = a["cadre"]
            moral += s
            moral_items.append({"key": "organization", "recordId": rid,
                                "label": f"学生干部（{post}）", "score": s})
        for rid, proj, level, s in a["moralHonors"]:
            if s:
                moral += s
                moral_items.append({"key": "honor", "recordId": rid,
                                    "label": f"{proj}（{level}）", "score": s})
        for rid, team in a["praIds"]:
            s = min(SPORTS["practice"]["perRecord"], SPORTS["practice"]["cap"])
            sports += s
            sports_items.append({"key": "practice", "recordId": rid,
                                 "label": team or "社会实践", "score": s})
        for rid, proj, level, s in a["sportsHonors"]:
            if s:
                sports += s
                sports_items.append({"key": "honor", "recordId": rid,
                                     "label": f"{proj}（{level}）", "score": s})
        moral, sports = min(moral, MORAL["cap"]), min(sports, SPORTS["cap"])

        inn_items, inn_bonus = [], 0.0
        for rid, cat, proj, credit in sorted(a["innItems"], key=lambda x: -x[3]):
            if inn_bonus >= COMPREHENSIVE_RULE["innovation"]["cap"]:
                break
            used = min(credit, COMPREHENSIVE_RULE["innovation"]["cap"] - inn_bonus)
            inn_bonus += used
            inn_items.append({"key": CAT_KEY.get(cat, "inn_other"), "recordId": rid,
                              "label": f"{INNOVATE_KV[cat]['label']}：{proj}", "score": round(used, 2)})

        w = COMPREHENSIVE_RULE["weights"]
        total = academic * w["academic"] + moral * w["moral"] + sports * w["sports"] + inn_bonus
        out.append({
            "sid": u.id, "uid": u.uid, "name": u.name,
            "classId": u.classId, "major": u.major, "periods": u.periods,
            "academic": {"gpa": g["gpa"] if g else None, "score": academic,
                         "semester": g["semester"] if g else None},
            "imported": ({"comp": g["comp"], "compRank": g["compRank"], "maxRank": g["maxRank"]}
                         if g else None),
            "moral": {"base": MORAL["base"], "score": round(moral, 2), "items": moral_items},
            "sports": {"base": SPORTS["base"], "score": round(sports, 2), "items": sports_items},
            "innovation": {"bonus": round(inn_bonus, 2), "items": inn_items,
                           "capped": sum(x[3] for x in a["innItems"]) > COMPREHENSIVE_RULE["innovation"]["cap"]},
            "total": round(total, 2),
            "majorRank": 0, "majorSize": 0,
        })

    # 专业内排名（同年级同专业，总分从高到低严格顺序编号 1~N，直观易读）
    groups: dict[tuple, list[dict]] = {}
    for r in out:
        groups.setdefault((r["periods"], r["major"]), []).append(r)
    for members in groups.values():
        members.sort(key=lambda x: -x["total"])
        for i, r in enumerate(members):
            r["majorRank"] = i + 1
            r["majorSize"] = len(members)
    # 仅返回目标学生（排名已按完整年级×专业口径计算）
    target_ids = {u.id for u in targets}
    return [r for r in out if r["sid"] in target_ids]
