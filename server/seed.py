"""演示数据种子 + 数据集导出（哈工大威海 · 汽车工程学院口径）

运行 python seed.py：
1. 重建演示库：院长 1 + 辅导员 4 + 学生 1200（4 个年级 × 300）+ 全实体真实分布记录
2. 在 dataset/ 导出全套 CSV 数据集（utf-8-sig，Excel 可直接打开）
演示账号：学生 202300001~202300012（2023级车辆2301班）· 辅导员 C0001~C0004 · 院长 D0001，密码均 123456
"""
import asyncio
import csv
import random
from pathlib import Path

from sqlalchemy import select

from app.meta import AWARD_POST, INNOVATE_KV, PARTY_TYPE
from app.models.database import (AsyncSessionLocal, Certificate, Experience,
                                 GpaComp, Honor, Innovation, Organization,
                                 Party, Practice, User, Voluntary, gen_id,
                                 init_db)
from app.security import hash_password
from app.services.credits import assess_inn_credit

random.seed(20260904)  # 固定随机种子，数据可复现

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
COLLEGE = "汽车工程学院"

# 专业 -> (班级代号, 班级数, 每级总人数)
MAJORS = [("车辆工程", "车辆", 4, 136), ("能源与动力工程", "能动", 2, 68),
          ("机械设计制造及其自动化", "机电", 2, 66), ("交通运输", "交通", 1, 30)]
GRADES = ["2023", "2024", "2025", "2026"]

# 辅导员按「年级×专业」带班：每年级每专业 1 名（专业内分几个班），院长全院统筹
COUNSELLORS = [
    ("C0001", "李文静", "2023", "车辆工程"), ("C0002", "张伟", "2024", "车辆工程"),
    ("C0003", "陈晓宇", "2025", "车辆工程"), ("C0004", "赵倩", "2026", "车辆工程"),
    ("C0005", "王海燕", "2023", "能源与动力工程"), ("C0006", "周建军", "2024", "能源与动力工程"),
    ("C0007", "吴敏", "2025", "能源与动力工程"), ("C0008", "郑立群", "2026", "能源与动力工程"),
    ("C0009", "刘志强", "2023", "机械设计制造及其自动化"), ("C0010", "孙丽华", "2024", "机械设计制造及其自动化"),
    ("C0011", "杨光辉", "2025", "机械设计制造及其自动化"), ("C0012", "冯晓梅", "2026", "机械设计制造及其自动化"),
    ("C0013", "赵鹏", "2023", "交通运输"), ("C0014", "钱雅琴", "2024", "交通运输"),
    ("C0015", "蒋明辉", "2025", "交通运输"), ("C0016", "沈国栋", "2026", "交通运输"),
]
DEAN = ("D0001", "王建国")

# 年级画像：审核通过率 / 各类记录期望条数（小数为概率加 1）/ 已完成学期数
PROFILE = {
    "2023": dict(pass_p=0.85, practice=2, voluntary=3, honor=2, certificate=2, org=0.7, party=0.85, sems=6),
    "2024": dict(pass_p=0.72, practice=2, voluntary=2, honor=1.5, certificate=1, org=0.5, party=0.5, sems=4),
    "2025": dict(pass_p=0.55, practice=1, voluntary=2, honor=1, certificate=0.8, org=0.3, party=0.25, sems=2),
    "2026": dict(pass_p=0.25, practice=0, voluntary=1, honor=0, certificate=0, org=0.05, party=0.1, sems=0),
}

SURNAMES = "王李张刘陈杨赵黄周吴徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
GIVEN_M = ["浩然", "子轩", "俊杰", "宇轩", "博文", "思远", "天佑", "志强", "嘉树", "承宇", "泽楷", "昊天", "明哲", "景行", "云舟", "亦驰", "沛东", "庆丰", "家豪", "宗翰", "雨泽", "鸿飞", "振宇", "书航", "朗峰", "启铭", "向阳", "文博", "致远", "立群"]
GIVEN_F = ["雨桐", "诗涵", "梦琪", "欣怡", "语嫣", "紫萱", "若曦", "静姝", "佳琪", "思颖", "悦宁", "芷若", "书瑶", "梦洁", "雪晴", "采薇", "依琳", "婉清", "静怡", "晓萱", "嘉懿", "清扬", "慕青", "映真", "海宁", "芳菲", "慧中", "乐容", "雅雯", "丹妮"]

NATIONS = ["汉族", "汉族", "汉族", "汉族", "汉族", "汉族", "汉族", "汉族", "满族", "回族", "蒙古族", "壮族", "朝鲜族"]
ORIGINS = ["山东青岛", "山东济南", "山东烟台", "山东潍坊", "山东临沂", "山东淄博", "山东济宁",
           "河北石家庄", "河南郑州", "江苏徐州", "安徽合肥", "山西太原", "辽宁大连", "吉林长春", "黑龙江哈尔滨"]
PRACTICE_LOCS = ["临沂", "烟台", "青岛", "济南", "威海", "潍坊", "淄博", "济宁", "泰安", "聊城", "日照", "德州", "枣庄", "东营"]
PRACTICE_THEMES = ["乡村振兴调研", "红色基因传承", "社区志愿服务", "企业走访见习", "黄河流域生态考察",
                   "汽车产业链调研", "关爱留守儿童", "海洋生态保护宣传", "科技支农帮扶", "红色基地研学"]
PRACTICE_TYPES = ["校级重点团队", "院级重点团队", "自主实践团队", "返家乡实践", "企业实习实践"]
VOLUNTARY_POOL = ["校园迎新志愿服务", "国际沙滩音乐节志愿服务", "火车站春运暖冬行动", "社区敬老院慰问服务",
                  "威海国际马拉松赛事保障", "图书馆图书整理志愿岗", "义务家教进社区", "海边环保净滩行动",
                  "无偿献血宣传服务", "科技馆讲解志愿者", "防艾知识宣传志愿活动", "校企合作车展引导志愿"]
HONOR_POOL = [("校三好学生", "校级"), ("校优秀学生干部", "校级"), ("国家奖学金", "国家级"),
              ("国家励志奖学金", "国家级"), ("校一等奖学金", "校级"), ("校二等奖学金", "校级"),
              ("校三等奖学金", "校级"), ("优秀共青团员", "校级"), ("优秀共青团干部", "校级"),
              ("社会实践先进个人", "校级"), ("军训优秀学员", "院级"), ("校园十佳志愿者", "校级")]
HONOR_UNITS = ["学校", "校团委", "学生工作处", COLLEGE]
CERT_POOL = [("大学英语四级证书", lambda: f"7100{random.randint(100000, 999999)}"),
             ("大学英语六级证书", lambda: f"6400{random.randint(100000, 999999)}"),
             ("全国计算机等级考试二级证书", lambda: f"{random.randint(51, 64)}{random.randint(1000000, 9999999)}"),
             ("机动车驾驶证（C1）", lambda: f"3706{random.randint(100000, 999999)}"),
             ("普通话水平测试二级甲等证书", lambda: f"{random.randint(3700, 3799)}{random.randint(10000, 99999)}"),
             ("AutoCAD 机械设计工程师认证", lambda: f"CAD{random.randint(100000, 999999)}")]
ORG_POOL = [("校学生会", "学生会组织", ["主席团", "部长", "干事"]),
            (f"{COLLEGE}学生会", "学生会组织", ["部长", "干事"]),
            ("FSAE方程式赛车队", "科技类社团", ["队长", "技术负责人", "成员"]),
            ("智能汽车协会", "科技类社团", ["副社长", "技术负责人", "成员"]),
            ("校辩论队", "文艺体育社团", ["成员"]),
            ("校篮球协会", "文艺体育社团", ["成员"])]
CHAIR_TOPICS = ["智能网联汽车技术前沿", "新能源汽车动力总成发展趋势", "氢能及燃料电池汽车产业展望",
                "汽车轻量化设计与新材料应用", "智能制造与数字化工厂实践", "车载总线与嵌入式系统开发",
                "无人驾驶环境感知技术进展", "汽车空气动力学优化设计", "动力电池热管理关键技术", "汽车芯片与域控制器架构"]
COMP_POOL = [("中国大学生方程式汽车大赛", ["国家级"]),
             ("全国大学生智能汽车竞赛", ["国家级", "省级"]),
             ("全国大学生数学建模竞赛", ["国家级", "省级"]),
             ("全国大学生机械创新设计大赛", ["国家级", "省级"]),
             ("全国大学生节能减排社会实践与科技竞赛", ["国家级", "省级"]),
             ("中国国际大学生创新大赛", ["国家级", "省级"]),
             ("挑战杯全国大学生课外学术科技作品竞赛", ["国家级", "省级"]),
             ("山东省大学生机电产品创新设计竞赛", ["省级", "校级"]),
             ("校智能车校内选拔赛", ["校级"])]
PROJECT_POOL = ["基于机器视觉的行人过街检测系统", "智能导览机器人设计与实现", "新能源汽车电池热管理优化研究",
                "基于STM32的智能循迹小车", "氢燃料电池汽车散热性能仿真分析", "基于深度学习的交通标志识别系统",
                "车载OBD数据采集与驾驶行为分析", "太阳能小车能量管理策略研究", "二手车价格预测模型构建",
                "校园共享电动车调度优化研究", "汽车内饰件轻量化设计", "轮胎花纹与湿滑路面制动性能仿真"]
PAPER_POOL = ["基于深度学习的路面裂缝检测方法研究", "电动汽车无线充电耦合机构优化设计",
              "混合动力汽车能量管理策略仿真", "基于多目标优化的车身结构轻量化设计",
              "燃料电池汽车氢气循环系统特性分析", "基于YOLO的车距保持辅助算法研究",
              "低温环境下锂电池充放电特性研究", "汽车主动悬架半主动控制策略仿真"]
PATENT_POOL = ["一种电动汽车电池包液冷结构", "一种车载智能空气净化装置", "一种多功能汽车后备箱收纳架",
               "一种基于视觉的后视镜盲区监测装置", "一种新能源汽车充电枪锁止机构", "一种可调节角度的车载平板支架"]
ENTERPRISE_POOL = ["校园二手书流转平台", "新能源汽车科普工作室", "智能驾培服务平台", "大学生汽车文创工作室",
                   "校内共享打印服务站", "二手车检测陪购服务工作室"]
OTHER_POOL = ["全国大学生汽车科技夏令营", "暑期高校科学营活动", "汽车工程学院企业行",
              "德国亚琛工业大学线上交流项目", "智能驾驶技术专题培训", "汽车造型设计工作坊"]

_used_names: set[str] = set()


def make_name(sex: str) -> str:
    while True:
        n = random.choice(SURNAMES) + random.choice(GIVEN_M if sex == "男" else GIVEN_F)
        if n not in _used_names:
            _used_names.add(n)
            return n


def rand_date(y0: int, y1: int) -> str:
    y0, y1 = min(y0, y1), max(y0, y1)
    y = random.randint(y0, y1)
    m = random.randint(1, 8 if y >= 2026 else 12)  # 不生成未来日期
    return f"{y}-{m:02d}-{random.randint(1, 28):02d}"


def pick_count(n: float) -> int:
    return int(n) + (1 if random.random() < n % 1 else 0)


def roll_status(pass_p: float) -> str:
    r = random.random()
    if r < pass_p:
        return "通过"
    return "待审核" if r < pass_p + 0.18 else "驳回"


def audit(status: str, cname: str) -> tuple[str | None, str | None]:
    if status == "通过":
        return cname, random.choice(["材料齐全，同意认定", "佐证材料完整，予以通过", "符合认定条件，通过"])
    if status == "驳回":
        return cname, random.choice(["材料不完整，请补充佐证后重新提交", "时间信息有误，请核对后重新提交",
                                     "认定依据不足，请补充说明材料", "盖章缺失，请重新上传完整材料"])
    return None, None


def kv_pick(cat: str, weights: list[str] | None = None) -> tuple[str, str, float]:
    kv = INNOVATE_KV[cat]["kv"]
    chiefly = random.choices(list(kv), weights=weights)[0] if weights else random.choice(list(kv))
    minor = random.choice(list(kv[chiefly]))
    return chiefly, minor, float(kv[chiefly][minor])


# CSV 中文表头映射（英文键 -> 中文列名）
CSV_MAPS = {
    "students.csv": (["学号", "姓名", "性别", "民族", "政治面貌", "出生日期", "手机", "邮箱", "年级",
                      "学院", "专业", "班级", "生源地", "辅导员工号"],
                     {"uid": "学号", "name": "姓名", "sex": "性别", "nation": "民族",
                      "politicsStatus": "政治面貌", "birthday": "出生日期", "phone": "手机",
                      "email": "邮箱", "periods": "年级", "college": "学院", "major": "专业",
                      "classId": "班级", "origin": "生源地", "counsellorUid": "辅导员工号"}),
    "staff.csv": (["工号", "姓名", "角色", "职称", "手机"],
                  {"uid": "工号", "name": "姓名", "role": "角色", "title": "职称", "phone": "手机"}),
    "practices.csv": (["学号", "团队名称", "类型", "主题", "主办单位", "开始日期", "结束日期", "状态", "审核人", "审核意见"],
                      {"sid": "学号", "team": "团队名称", "type": "类型", "theme": "主题", "sponsor": "主办单位",
                       "startDate": "开始日期", "endDate": "结束日期", "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "voluntarys.csv": (["学号", "项目名称", "时长(小时)", "组织单位", "状态", "审核人", "审核意见"],
                       {"sid": "学号", "project": "项目名称", "duration": "时长(小时)", "sponsor": "组织单位",
                        "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "innovations.csv": (["学号", "类别", "名称", "补充说明", "获奖情况", "人员次序", "获得日期", "结题时间", "认定学分", "状态", "审核人", "审核意见"],
                        {"sid": "学号", "category": "类别", "project": "名称", "implementation": "补充说明",
                         "honor": "获奖情况", "post": "人员次序", "date": "获得日期", "deadline": "结题时间",
                         "credit": "认定学分", "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "honors.csv": (["学号", "荣誉名称", "级别", "授予单位", "获得日期", "状态", "审核人", "审核意见"],
                   {"sid": "学号", "project": "荣誉名称", "level": "级别", "team": "授予单位",
                    "date": "获得日期", "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "certificates.csv": (["学号", "证书名称", "证书编号", "获得日期", "状态", "审核人", "审核意见"],
                         {"sid": "学号", "project": "证书名称", "code": "证书编号", "date": "获得日期",
                          "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "organizations.csv": (["学号", "组织名称", "组织类型", "职务", "开始日期", "结束日期", "状态", "审核人", "审核意见"],
                          {"sid": "学号", "team": "组织名称", "type": "组织类型", "post": "职务",
                           "startDate": "开始日期", "endDate": "结束日期", "status": "状态",
                           "auditor": "审核人", "opinion": "审核意见"}),
    "parties.csv": (["学号", "日期", "阶段", "党支部", "介绍人", "培养联系人", "状态", "审核人", "审核意见"],
                    {"sid": "学号", "date": "日期", "type": "阶段", "department": "党支部", "boss": "介绍人",
                     "leader": "培养联系人", "status": "状态", "auditor": "审核人", "opinion": "审核意见"}),
    "gpa.csv": (["学号", "学期", "学院", "专业", "互评成绩", "综测成绩", "GPA", "GPA排名", "综测排名", "专业人数"],
                {"sid": "学号", "semester": "学期", "college": "学院", "major": "专业", "mutual": "互评成绩",
                 "comp": "综测成绩", "gpa": "GPA", "gpaRank": "GPA排名", "compRank": "综测排名", "maxRank": "专业人数"}),
    "experiences.csv": (["学号", "开始日期", "结束日期", "学院", "专业", "班级", "见证人"],
                        {"sid": "学号", "startDate": "开始日期", "endDate": "结束日期", "college": "学院",
                         "major": "专业", "classId": "班级", "eyewitness": "见证人"}),
}
INN_CAT_ZH = {"chair": "前沿学术报告", "project": "年度创新创业项目", "competition": "科技创新竞赛",
              "enterprise": "创业实践", "paper": "学术论文", "patent": "申请专利", "other": "其他实践活动"}

# 实体 key -> (CSV 文件, innovations 内的类别中文名)；用于把库内状态重分布同步进 CSV 快照
_ENTITY_CSV = {
    "practice": ("practices.csv", None), "voluntary": ("voluntarys.csv", None),
    "inn_chair": ("innovations.csv", INN_CAT_ZH["chair"]),
    "inn_project": ("innovations.csv", INN_CAT_ZH["project"]),
    "inn_competition": ("innovations.csv", INN_CAT_ZH["competition"]),
    "inn_enterprise": ("innovations.csv", INN_CAT_ZH["enterprise"]),
    "inn_paper": ("innovations.csv", INN_CAT_ZH["paper"]),
    "inn_patent": ("innovations.csv", INN_CAT_ZH["patent"]),
    "inn_other": ("innovations.csv", INN_CAT_ZH["other"]),
    "honor": ("honors.csv", None), "certificate": ("certificates.csv", None),
    "organization": ("organizations.csv", None), "party": ("parties.csv", None),
}


def _sync_csv_status(csv_rows: dict, flips: list, opinion: str | None):
    """库内状态重分布同步到 CSV 快照：按 (文件, 类别) 取等量「通过」行翻状态，保持口径一致"""
    from collections import Counter
    for (name, zh), n in Counter((f, zh) for f, zh, _ in flips).items():
        pool = [r for r in csv_rows.get(name, []) if r["status"] == "通过"
                and (zh is None or r.get("category") == zh)]
        for r in random.sample(pool, min(n, len(pool))):
            r["status"] = "待院长审批" if opinion else "公示中"
            if opinion:
                r["opinion"] = opinion


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(User).limit(1))).scalar_one_or_none():
            print("数据库已有数据，跳过种子（如需重建请删除 growth_dev.db 后重试）")
            return

        pwd_hash = hash_password("123456")  # 同密码只算一次 bcrypt，全库复用
        csv_rows: dict[str, list[dict]] = {name: [] for name in CSV_MAPS}

        dean = User(uid=DEAN[0], name=DEAN[1], role="Dean", title="副院长",
                    college=COLLEGE, passwordHash=pwd_hash)
        db.add(dean)
        csv_rows["staff.csv"].append({"uid": dean.uid, "name": dean.name, "role": "Dean",
                                      "title": dean.title, "phone": "", "college": COLLEGE})
        couns: list[User] = []
        couns_map: dict[tuple[str, str], User] = {}   # (年级, 专业) → 辅导员
        for uid, name, g, major in COUNSELLORS:
            u = User(uid=uid, name=name, role="Counsellor", title=f"{g}级{major}辅导员",
                     college=COLLEGE, phone=f"138{random.randint(0, 99999999):08d}",
                     passwordHash=pwd_hash)
            db.add(u)
            couns.append(u)
            couns_map[(g, major)] = u
            csv_rows["staff.csv"].append({"uid": uid, "name": name, "role": "Counsellor",
                                          "title": u.title, "phone": u.phone,
                                          "college": COLLEGE})
        await db.flush()

        seq = 0
        n_inn = n_rec = 0
        for g in GRADES:
            prof = PROFILE[g]
            # 本级班级序列：车辆2301-2304 / 能动2301-2302 / 机电2301-2302 / 交通2301
            classes = []
            for major, code, n_class, total in MAJORS:
                base, extra = divmod(total, n_class)
                for c in range(1, n_class + 1):
                    classes.append((major, code, c, base + (1 if c <= extra else 0), total))
            for major, code, c, n_stu, major_total in classes:
                couns_of = couns_map[(g, major)]
                other_couns = [u.name for u in couns if u.id != couns_of.id] + [DEAN[1]]
                class_id = f"{code}{g[2:]}{c:02d}班"
                for _ in range(n_stu):
                    seq += 1
                    uid = f"{g}{seq:05d}"
                    sex = "男" if random.random() < 0.72 else "女"
                    politics = random.choices(
                        ["中共党员", "预备党员", "共青团员", "群众"],
                        weights={"2023": [12, 15, 60, 13], "2024": [0, 8, 70, 22],
                                 "2025": [0, 0, 80, 20], "2026": [0, 0, 75, 25]}[g])[0]
                    s = User(
                        id=gen_id(), uid=uid, name=make_name(sex), role="Student", sex=sex,
                        nation=random.choice(NATIONS), politicsStatus=politics,
                        birthday=f"{int(g) - 18}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
                        phone=f"1{random.choice('35789')}{random.randint(0, 999999999):09d}",
                        email=f"{uid}@hitwh.edu.cn", classId=class_id, periods=f"{g}级",
                        college=COLLEGE, major=major,
                        origin=random.choice(ORIGINS), counsellorId=couns_of.id,
                        passwordHash=pwd_hash)
                    db.add(s)
                    csv_rows["students.csv"].append({
                        "uid": uid, "name": s.name, "sex": sex, "nation": s.nation,
                        "politicsStatus": politics, "birthday": s.birthday, "phone": s.phone,
                        "email": s.email, "periods": s.periods, "college": COLLEGE,
                        "major": major, "classId": class_id, "origin": s.origin,
                        "counsellorUid": couns_of.uid})

                    def A(payload: dict):
                        nonlocal n_rec
                        n_rec += 1
                        return payload

                    # ---- 社会实践 ----
                    for j in range(pick_count(prof["practice"])):
                        if j >= 2:
                            break
                        theme = random.choice(PRACTICE_THEMES)
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        y = int(g) + 1 + j
                        team = f"赴{random.choice(PRACTICE_LOCS)}{theme[:4]}实践团"
                        ptype = random.choice(PRACTICE_TYPES)
                        sponsor = random.choice([COLLEGE, "校团委", "威海团市委"])
                        sd, ed = f"{y}-07-{random.randint(1, 10):02d}", f"{y}-07-{random.randint(15, 28):02d}"
                        db.add(Practice(sid=s.id, team=team, type=ptype,
                                        theme=theme, sponsor=sponsor, startDate=sd, endDate=ed,
                                        status=st, auditor=au, opinion=op))
                        csv_rows["practices.csv"].append(
                            {"sid": uid, "team": team, "type": ptype, "theme": theme, "sponsor": sponsor,
                             "startDate": sd, "endDate": ed, "status": st, "auditor": au, "opinion": op})
                    # ---- 志愿服务 ----
                    for j in range(pick_count(prof["voluntary"])):
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        proj = random.choice(VOLUNTARY_POOL)
                        dur = random.choice([8, 12, 16, 20, 24, 32, 40, 48])
                        sponsor = random.choice(["校团委", "校青年志愿者协会", COLLEGE, "威海团市委"])
                        db.add(A(Voluntary(sid=s.id, project=proj, duration=dur,
                                           sponsor=sponsor, status=st, auditor=au, opinion=op)))
                        csv_rows["voluntarys.csv"].append(
                            {"sid": uid, "project": proj, "duration": dur, "sponsor": sponsor,
                             "status": st, "auditor": au, "opinion": op})
                    # ---- 创新创业 ----
                    # 在校生（2023-2025 级）7 类各一条，保证每个板块都有数据；2026 级新生仅 1 条讲座
                    inn_cats = (["chair"] if g == "2026" else
                                ["chair", "project", "competition",
                                 "enterprise", "paper", "patent", "other"])
                    for cat in inn_cats:
                        d = {"sid": s.id, "category": cat, "status": roll_status(prof["pass_p"])}
                        d["auditor"], d["opinion"] = audit(d["status"], couns_of.name)
                        if cat == "chair":
                            chiefly, minor, credit = kv_pick("chair", [55, 15, 30])
                            chair_date = (f"2026-09-{random.randint(1, 5):02d}" if g == "2026"
                                          else rand_date(min(int(g) + 1, 2026), 2026))
                            d.update(project=chiefly, implementation=f"{minor}·{random.choice(CHAIR_TOPICS)}",
                                     credit=credit, date=chair_date)
                        elif cat == "competition":
                            name, levels = random.choice(COMP_POOL)
                            chiefly, minor, _ = kv_pick("competition", [3, 30, 40, 27])
                            if chiefly not in levels:  # 竞赛名与级别不符时落到该竞赛允许的最高级别
                                chiefly = levels[0]
                                minor = random.choice(list(INNOVATE_KV["competition"]["kv"][chiefly]))
                            post = random.choice(AWARD_POST[:5])
                            # 学分 = 规则矩阵基准分 × 人员次序系数（与运行时核定同一函数）
                            d.update(project=name, honor=f"{chiefly}·{minor}", post=post,
                                     credit=assess_inn_credit("competition", chiefly, minor, post),
                                     date=rand_date(min(int(g) + 1, 2026), 2026))
                        elif cat == "project":
                            chiefly, minor, credit = kv_pick("project", [10, 30, 40, 20])
                            d.update(project=f"{chiefly}·{minor}",
                                     implementation=random.choice(PROJECT_POOL),
                                     post=minor, deadline=f"{int(g) + 3}-06-30",
                                     credit=credit, date=rand_date(min(int(g) + 1, 2025), 2025))
                        elif cat == "paper":
                            chiefly, minor, credit = kv_pick("paper", [8, 22, 30, 40])
                            d.update(project=random.choice(PAPER_POOL), implementation=f"{chiefly}·{minor}",
                                     post=minor, credit=credit, date=rand_date(min(int(g) + 2, 2026), 2026))
                        elif cat == "patent":
                            chiefly, minor, credit = kv_pick("patent", [20, 55, 25])
                            d.update(project=random.choice(PATENT_POOL), implementation=f"{chiefly}·{minor}",
                                     post=minor, credit=credit, date=rand_date(min(int(g) + 2, 2026), 2026))
                        elif cat == "enterprise":
                            chiefly, minor, credit = kv_pick("enterprise")
                            d.update(project=random.choice(ENTERPRISE_POOL), implementation=f"{chiefly}·{minor}",
                                     post=minor, credit=credit, date=rand_date(min(int(g) + 2, 2026), 2026))
                        else:
                            chiefly, minor, credit = kv_pick("other")
                            d.update(project=random.choice(OTHER_POOL), implementation=f"{chiefly}·{minor}",
                                     credit=credit, date=rand_date(min(int(g) + 1, 2026), 2026))
                        d = {k: v for k, v in d.items() if v is not None}
                        db.add(A(Innovation(**d)))
                        n_inn += 1
                        csv_rows["innovations.csv"].append(
                            {"sid": uid, "category": INN_CAT_ZH[cat], "project": d.get("project"),
                             "implementation": d.get("implementation"), "honor": d.get("honor"),
                             "post": d.get("post"), "date": d.get("date"), "deadline": d.get("deadline"),
                             "credit": d.get("credit"), "status": d["status"], "auditor": d.get("auditor"),
                             "opinion": d.get("opinion")})
                    # ---- 荣誉 / 证书 / 组织 / 入党 ----
                    for j in range(pick_count(prof["honor"])):
                        proj, level = random.choice(HONOR_POOL)
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        team, hdate = random.choice(HONOR_UNITS), rand_date(int(g), 2026)
                        db.add(A(Honor(sid=s.id, project=proj, level=level, team=team,
                                       date=hdate, status=st, auditor=au, opinion=op)))
                        csv_rows["honors.csv"].append(
                            {"sid": uid, "project": proj, "level": level, "team": team,
                             "date": hdate, "status": st, "auditor": au, "opinion": op})
                    for j in range(pick_count(prof["certificate"])):
                        proj, codefn = random.choice(CERT_POOL)
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        code, cdate = codefn(), rand_date(int(g), 2026)
                        db.add(A(Certificate(sid=s.id, project=proj, code=code, date=cdate,
                                             status=st, auditor=au, opinion=op)))
                        csv_rows["certificates.csv"].append(
                            {"sid": uid, "project": proj, "code": code, "date": cdate,
                             "status": st, "auditor": au, "opinion": op})
                    if random.random() < prof["org"]:
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        if random.random() < 0.25:  # 班团委经历
                            team, otype = class_id, "班团委"
                            post = random.choice(["班长", "团支书", "学习委员", "体育委员", "文艺委员"])
                        else:
                            team, otype, posts = random.choice(ORG_POOL)
                            post = random.choice(posts)
                        sd, ed = f"{int(g)}-09-01", f"{int(g) + 1}-09-01"
                        db.add(A(Organization(
                            sid=s.id, team=team, type=otype, post=post,
                            startDate=sd, endDate=ed, status=st, auditor=au, opinion=op)))
                        csv_rows["organizations.csv"].append(
                            {"sid": uid, "team": team, "type": otype, "post": post,
                             "startDate": sd, "endDate": ed, "status": st,
                             "auditor": au, "opinion": op})
                    if random.random() < prof["party"]:
                        top = {"2023": 4, "2024": 3, "2025": 2, "2026": 1}[g]
                        idx = random.randint(1 if g != "2026" else 0, top)
                        st = roll_status(prof["pass_p"])
                        au, op = audit(st, couns_of.name)
                        ptype = PARTY_TYPE[idx]
                        pdate = f"{int(g) + idx // 2}-{random.randint(idx * 2 + 1, 12):02d}-{random.randint(1, 28):02d}"
                        boss = random.choice(other_couns) if idx >= 3 else None
                        db.add(A(Party(
                            sid=s.id, type=ptype, date=pdate,
                            department=f"{COLLEGE}学生党支部",
                            boss=boss, leader=couns_of.name, status=st, auditor=au, opinion=op)))
                        csv_rows["parties.csv"].append(
                            {"sid": uid, "date": pdate, "type": ptype, "department": f"{COLLEGE}学生党支部",
                             "boss": boss, "leader": couns_of.name, "status": st,
                             "auditor": au, "opinion": op})
                    # ---- 成绩 + 教育经历 ----
                    for k in range(prof["sems"]):
                        sem = f"{int(g) + k // 2}-{int(g) + 1 + k // 2}-{k % 2 + 1}"
                        mutual, comp = round(70 + random.random() * 25, 1), round(68 + random.random() * 28, 1)
                        # 排名口径：同年级同专业（评奖/保研的天然口径），maxRank=专业人数
                        gpa, rk = round(2.7 + random.random() * 1.3, 2), random.randint(1, major_total)
                        db.add(A(GpaComp(
                            sid=s.id, semester=sem, college=COLLEGE, major=major,
                            mutual=mutual, comp=comp, gpa=gpa,
                            gpaRank=rk, compRank=random.randint(1, major_total), maxRank=major_total)))
                        csv_rows["gpa.csv"].append(
                            {"sid": uid, "semester": sem, "college": COLLEGE, "major": major,
                             "mutual": mutual, "comp": comp, "gpa": gpa, "gpaRank": rk,
                             "compRank": rk, "maxRank": major_total})
                    db.add(A(Experience(sid=s.id, startDate=f"{g}-09-01", endDate=f"{int(g) + 4}-07-01",
                                        college=COLLEGE, major=major, classId=class_id,
                                        eyewitness=couns_of.name)))
                    csv_rows["experiences.csv"].append(
                        {"sid": uid, "startDate": f"{g}-09-01", "endDate": f"{int(g) + 4}-07-01",
                         "college": COLLEGE, "major": major, "classId": class_id,
                         "eyewitness": couns_of.name})
            await db.commit()
            print(f"  {g}级 300 人已写入…")

        await db.commit()

        # ---- 多级审核流演示数据 ----
        # 从「通过」池划出：① dean_review 类（竞赛/论文/专利/创业/荣誉）→ 待院长审批（辅导员已初审）
        # ② 少量 → 公示中（约半数公示期已过，首次请求即被惰性晋升为「通过」，演示自动生效）
        from datetime import timedelta
        from app.models.database import now
        from app.services.audit_flow import STATUS_DEAN, STATUS_PUBLIC
        from app.services.entity_registry import ENTITY_REGISTRY, category_scope
        ts_now = now()
        n_dean = n_pub = 0
        dean_zh_flip, pub_zh_flip = [], []          # (csv文件, 类别中文名, 行) 与库内同步
        for key, e in ENTITY_REGISTRY.items():
            q = select(e.model).where(e.model.status == "通过")
            cat = category_scope(key, e.model)
            if cat is not None:
                q = q.where(cat)
            rows = (await db.execute(q)).scalars().all()
            csv_name, zh = _ENTITY_CSV.get(key, (None, None))
            if e.dean_review and rows:              # 初审通过转院长审批（约 8%）
                for r in random.sample(rows, max(1, len(rows) // 12)):
                    r.status, r.opinion = STATUS_DEAN, "初审通过，转院长审批"
                    n_dean += 1
                    if csv_name:
                        dean_zh_flip.append((csv_name, zh, r))
                    rows.remove(r)
            if rows:                                # 终审通过进公示（约 4%，其中一半已过期）
                for r in random.sample(rows, max(1, len(rows) // 25)):
                    r.status = STATUS_PUBLIC
                    end = ((ts_now - timedelta(hours=random.randint(1, 72))) if random.random() < 0.5
                           else (ts_now + timedelta(days=random.randint(1, 7))))
                    r.publicEnd = end.strftime("%Y-%m-%d %H:%M:%S")
                    n_pub += 1
                    if csv_name:
                        pub_zh_flip.append((csv_name, zh, r))
        await db.commit()
        _sync_csv_status(csv_rows, dean_zh_flip, "初审通过，转院长审批")
        _sync_csv_status(csv_rows, pub_zh_flip, None)

        # ---- 公示异议演示数据（公示监督闭环：实名异议 → 院长复核） ----
        # ① 一条「待复核」（同时演示待复核异议锁定惰性晋升）② 一条已复核「不成立」（维持认定）
        from app.models.database import Objection
        from app.services.oplog import build_log, record_title
        demo_students = (await db.execute(select(User).where(
            User.role == "Student",
            User.uid.in_([f"2023000{i}" for i in range(1, 13)])))).scalars().all()
        ts = ts_now.strftime("%Y-%m-%d %H:%M:%S")
        n_obj = 0
        for key, e in ENTITY_REGISTRY.items():
            if n_obj >= 2:
                break
            q = select(e.model).where(e.model.status == STATUS_PUBLIC,
                                      e.model.publicEnd > ts)
            cat = category_scope(key, e.model)
            if cat is not None:
                q = q.where(cat)
            rec = (await db.execute(q.limit(1))).scalar()
            objector = next((s for s in demo_students if rec is not None and s.id != rec.sid), None)
            if rec is None or objector is None:
                continue
            title = record_title(e, {f.name: getattr(rec, f.name, None) for f in e.fields})[:120]
            reason, status = (("公示材料中获奖级别与证书图片不一致，申请复核", "待复核") if n_obj == 0
                              else ("该同学参赛名单中未见其姓名，请学院核实", "不成立"))
            db.add(Objection(key=key, recordId=rec.id, recordLabel=e.label, recordTitle=title,
                             sid=rec.sid, objectorUid=objector.uid, objectorName=objector.name,
                             reason=reason, status=status,
                             handledBy=None if n_obj == 0 else "王建国",
                             handledTime=None if n_obj == 0 else ts))
            db.add(build_log(objector.uid, objector.name, "Student", "audit",
                             f"对{e.label}《{title}》提出公示异议：{reason[:60]}",
                             key=key, label=e.label, record_id=rec.id, sid=rec.sid))
            if status == "不成立":
                dean_user = (await db.execute(select(User).where(User.role == "Dean").limit(1))).scalar()
                if dean_user:
                    db.add(build_log(dean_user.uid, dean_user.name, "Dean", "audit",
                                     f"复核公示异议：{e.label}《{title}》异议不成立，维持认定",
                                     key=key, label=e.label, record_id=rec.id, sid=rec.sid))
            n_obj += 1

        # 存量记录合成操作日志（申报 + 审核留痕），保证日志页开箱有数据
        from app.services.oplog import backfill_oplogs
        n_log = await backfill_oplogs(db)
        # 存量驳回记录合成站内通知（历史置已读、近 7 天未读），保证通知中心开箱有数据
        from app.services.notify import backfill_notifications
        n_notif = await backfill_notifications(db)
        _dump_csv(csv_rows)
        total = sum(len(v) for v in csv_rows.values())
        print(f"种子完成：院长×1，辅导员×{len(couns)}，学生×{seq}，业务记录约 {n_rec} 条（创新创业 {n_inn} 条），"
              f"待院长审批 {n_dean} 条，公示中 {n_pub} 条，公示异议 {n_obj} 条，操作日志 {n_log} 条，站内通知 {n_notif} 条")
        print(f"CSV 数据集已导出至 {DATASET_DIR}（{len(csv_rows)} 个文件，共 {total} 行）")
        print("演示账号：学生 202300001~202300012 / 辅导员 C0001~C0016（年级×专业带班）/ 院长 D0001，密码均 123456")


def _dump_csv(csv_rows: dict[str, list[dict]]):
    DATASET_DIR.mkdir(exist_ok=True)
    for name, (head, mapping) in CSV_MAPS.items():
        with open(DATASET_DIR / name, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=head, extrasaction="ignore")
            w.writeheader()
            for row in csv_rows[name]:
                w.writerow({zh: row.get(k) for k, zh in mapping.items()})


if __name__ == "__main__":
    asyncio.run(seed())
