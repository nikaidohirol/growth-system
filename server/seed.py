"""演示数据种子：3 角色 + 12 学生 + 全实体记录 + 成绩/经历"""
import asyncio
import random

from passlib.context import CryptContext
from sqlalchemy import select

from app.models.database import (AsyncSessionLocal, Certificate, Experience,
                                 GpaComp, Honor, Innovation, Organization,
                                 Party, Practice, User, Voluntary, init_db)
from app.security import hash_password

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(User).limit(1))).scalar_one_or_none():
            print("数据库已有数据，跳过种子")
            return

        dean = User(uid="D0001", name="王建国", role="Dean", title="副院长",
                    passwordHash=hash_password("123456"))
        db.add(dean)

        counsellors = [
            User(uid="C0001", name="李文静", role="Counsellor", title="2023级辅导员",
                 phone="13800000001", passwordHash=hash_password("123456")),
            User(uid="C0002", name="张伟", role="Counsellor", title="2024级辅导员",
                 phone="13800000002", passwordHash=hash_password("123456")),
        ]
        db.add_all(counsellors)
        await db.flush()

        colleges = list({"计算机科学与技术学院": ["计算机科学与技术", "软件工程", "人工智能"],
                         "机械与汽车工程学院": ["车辆工程", "机械设计制造及其自动化"]}.items())
        students = []
        for i in range(12):
            college, majors = colleges[i % 2]
            major = majors[i % len(majors)]
            s = User(
                uid=f"2023{i + 1:04d}", name=f"学生{i + 1}", role="Student",
                sex="男" if i % 2 == 0 else "女", nation="汉族",
                politicsStatus=["群众", "共青团员", "预备党员", "中共党员"][i % 4],
                birthday=f"2005-0{i % 9 + 1}-1{i % 9}",
                phone=f"139{i:08d}", email=f"stu{i + 1}@hitwh.edu.cn",
                classId=f"20230{i % 3 + 1}班", periods="2023级",
                college=college, major=major,
                origin=["山东青岛", "山东济南", "河北石家庄", "河南郑州"][i % 4],
                counsellorId=counsellors[i % 2].id,
                passwordHash=hash_password("123456"))
            db.add(s)
            students.append(s)
        await db.flush()

        statuses = ["通过", "通过", "通过", "待审核", "驳回"]
        for idx, s in enumerate(students):
            # 社会实践 + 志愿服务
            for j in range(2):
                db.add(Practice(
                    sid=s.id, team=f"{s.college}赴威海暑期实践团{idx}{j}",
                    startDate=f"202{4 + j % 2}-07-01", endDate=f"202{4 + j % 2}-07-14",
                    type=["校级重点团队", "院级重点团队", "自主实践团队"][j % 3],
                    theme=["乡村振兴调研", "社区志愿服务", "企业走访见习"][j % 3],
                    sponsor=s.college, status=statuses[(idx + j) % 5],
                    auditor="李文静" if statuses[(idx + j) % 5] != "待审核" else None,
                    opinion="材料齐全，同意认定" if statuses[(idx + j) % 5] == "通过" else None))
            db.add(Voluntary(sid=s.id, project="校园迎新志愿服务", duration=20 + idx * 5,
                             sponsor="校团委", status=statuses[idx % 5]))
            # 创新创业
            inns = [
                ("chair", "汽车百家讲坛·第1-5期", None, None, None, None, 0.25),
                ("competition", f"全国大学生数学建模竞赛-{idx}", None, "国家级·二等奖",
                 "第一完成人", f"2024-11-{idx % 28 + 1:02d}", 4),
                ("project", "省级SRTP项目：智能导览机器人", None, "省级·负责人",
                 "负责人", None, 4),
            ]
            for cat, project, impl, honor, post, date, credit in inns:
                db.add(Innovation(
                    sid=s.id, category=cat, project=project,
                    implementation=impl or ("参加学术讲座并提交心得" if cat == "chair" else None),
                    honor=honor, post=post, date=date,
                    deadline="2025-06-30" if cat == "project" else None,
                    credit=credit, status=statuses[idx % 5]))
            # 荣誉 / 证书 / 组织 / 入党
            db.add(Honor(sid=s.id, project="校三好学生", level="校级",
                         team="学校", date="2024-12-01", status=statuses[(idx + 1) % 5]))
            db.add(Certificate(sid=s.id, project="大学英语六级证书",
                               code=f"6400{idx:06d}", date="2024-08-22",
                               status=statuses[(idx + 2) % 5]))
            db.add(Organization(sid=s.id, team="校学生会", type="学生会组织",
                                post="部长", startDate="2023-09-01", endDate="2024-09-01",
                                status=statuses[(idx + 3) % 5]))
            if idx % 3 == 0:
                db.add(Party(sid=s.id, type="确定为入党积极分子", date="2024-05-11",
                             department=f"{s.college}党支部", boss="张伟", leader="李文静",
                             status=statuses[idx % 5]))
            # 成绩 + 教育经历
            for sem_i, sem in enumerate(["2023-2024-1", "2023-2024-2"]):
                db.add(GpaComp(
                    sid=s.id, semester=sem, college=s.college, major=s.major,
                    mutual=80 + (idx * 3 + sem_i * 7) % 15, comp=78 + (idx * 5) % 20,
                    gpa=round(3.0 + (idx % 9) * 0.1 + sem_i * 0.05, 2),
                    gpaRank=idx + 1 + sem_i, compRank=idx + 1, maxRank=6))
            db.add(Experience(sid=s.id, startDate="2023-09-01", endDate="2027-07-01",
                              college=s.college, major=s.major, classId=s.classId,
                              eyewitness="李文静"))

        await db.commit()
        print(f"种子完成：dean×1, counsellor×2, student×12 + 全实体演示记录")
        print("演示账号：学生 20230001~20230012 / 辅导员 C0001 C0002 / 院长 D0001，密码均 123456")


if __name__ == "__main__":
    asyncio.run(seed())
