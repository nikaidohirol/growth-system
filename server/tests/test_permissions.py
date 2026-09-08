"""权限矩阵测试：pytest tests/test_permissions.py -q（需先 python seed.py）

三角色 × 关键端点的越权分支全覆盖：
    401 —— 未认证（无 token / 伪造签名 token）一律拒绝
    403 —— Student 不可触达任何管理端点；Counsellor 不可越级（院长专属操作）；
           辅导员只能操作「名下学生」（年级×专业带班 scope 隔离）
    404 —— 学生横向越权：读不到别人的申报记录（不暴露存在性）
    正向 —— Dean 全量可见，scope 交汇点行为正确
"""
import os
import uuid

os.environ.setdefault("LLM_API_KEY", "")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.meta as meta  # noqa: E402
from main import app  # noqa: E402

RUN = uuid.uuid4().hex[:6]   # 每次运行唯一后缀：失败残留数据不影响关键字检索断言


@pytest.fixture(autouse=True)
def _open_window(monkeypatch):
    """申报窗口全开，与运行日期解耦"""
    monkeypatch.setitem(meta.AUDIT_FLOW, "windowStart", "2000-01-01")
    monkeypatch.setitem(meta.AUDIT_FLOW, "windowEnd", "2099-12-31")


async def login(uid: str, password: str = "123456") -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/auth/login", json={"uid": uid, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["data"]["token"]


def client(token: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t",
                       headers={"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------- 401 未认证
async def test_unauthenticated_rejected():
    """无 token / 伪造 token / 签名不符的 JWT 一律 401，不区分端点"""
    from jose import jwt as jose_jwt

    no_auth = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    forged = AsyncClient(transport=ASGITransport(app=app), base_url="http://t",
                         headers={"Authorization": "Bearer fake.token.value"})
    wrong_key = AsyncClient(transport=ASGITransport(app=app), base_url="http://t",
                            headers={"Authorization": "Bearer " + jose_jwt.encode(
                                {"sub": "whatever", "role": "Dean", "exp": 4102444800},
                                "attacker-key", algorithm="HS256")})
    try:
        for c in (no_auth, forged, wrong_key):
            for url in ("/api/dashboard/dean", "/api/users/students",
                        "/api/audit/summary", "/api/logs", "/api/notifications"):
                assert (await c.get(url)).status_code == 401, url
    finally:
        await no_auth.aclose()
        await forged.aclose()
        await wrong_key.aclose()


# ------------------------------------------------- Student：不可触达管理端
async def test_student_blocked_from_admin_endpoints():
    stu = await login("202300001")
    async with client(stu) as c:
        # 审核中心（本测试文件配套加固了角色守卫：summary/records 仅限辅导员/院长）
        assert (await c.get("/api/audit/summary")).status_code == 403
        assert (await c.get("/api/audit/records", params={"key": "practice"})).status_code == 403
        # 院长专属批量确认 / 异议复核列表 / 操作日志 / 学生管理
        assert (await c.post("/api/audit/batch/practice", json={"ids": ["x"]})).status_code == 403
        assert (await c.get("/api/objections")).status_code == 403
        assert (await c.get("/api/logs")).status_code == 403
        assert (await c.get("/api/users/students")).status_code == 403
        assert (await c.post("/api/users/students", json=[])).status_code == 403
        # 教务数据录入（综合成绩）
        assert (await c.get("/api/gpa/list", params={"sid": "x"})).status_code == 403
        assert (await c.post("/api/gpa", json={"sid": "x", "semester": "1",
                                               "mutual": 80, "comp": 85, "gpa": 3.5,
                                               "gpaRank": 1, "compRank": 1, "maxRank": 30,
                                               "college": "x", "major": "x"})).status_code == 403
        assert (await c.post("/api/gpa/import", json={"rows": [{"uid": "202300001"}]})).status_code == 403
        # 审核操作本身（对自己名下记录：scope 判定先于角色判定，同为 403）
        rid = (await c.post("/api/entities/practice", json={
            "team": f"越权审核{RUN}", "type": "自主实践团队", "theme": "权限矩阵",
            "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
            "files": []})).json()["data"]["id"]
        assert (await c.post(f"/api/audit/submit/practice/{rid}",
                             json={"status": "通过", "opinion": "自己给自己批"})).status_code == 403
        assert (await c.delete(f"/api/entities/practice/{rid}")).json()["code"] == 0  # 待审核可删


# ------------------------------------------------- Counsellor：越级 + scope
async def test_counsellor_cannot_cross_level():
    coun = await login("C0001")
    async with client(coun) as c:
        # 不能替学生直接申报（申报通道仅学生；历史数据走 import 补录）
        r = await c.post("/api/entities/practice", json={
            "team": "辅导员代报", "type": "自主实践团队", "theme": "x", "sponsor": "x",
            "startDate": "2026-07-01", "endDate": "2026-07-10", "files": []})
        assert r.status_code == 403 and "仅学生" in r.json()["detail"]
        # 院长专属：批量确认 / 公示异议复核（角色守卫先于存在性校验）
        assert (await c.post("/api/audit/batch/practice", json={"ids": ["x"]})).status_code == 403
        assert (await c.post("/api/objections/no-such-id/review",
                             json={"result": "不成立"})).status_code == 403


async def test_counsellor_scope_isolation():
    """年级×专业带班隔离：C0001（2023 级车辆工程）管不到 2024 级学生（C0002 带班）"""
    stu1 = await login("202300001")
    coun1, dean = await login("C0001"), await login("D0001")
    # 院长名册里取一个 2024 级车辆工程学生（C0002 名下）
    async with client(dean) as c:
        lst = (await c.get("/api/users/students",
                           params={"keyword": "车辆24", "pageSize": 50})).json()
        assert lst["data"]["total"] >= 1, "种子数据应含 2024 级车辆工程学生"
        target = lst["data"]["list"][0]
    stu2 = await login(target["uid"])

    # stu1 申报一条记录：C0001 可见，C0002 不可见（数据权限隔离）
    async with client(stu1) as c:
        stu1_id = (await c.get("/api/auth/me")).json()["data"]["id"]
        rid = (await c.post("/api/entities/practice", json={
            "team": f"隔离验证团{RUN}", "type": "自主实践团队", "theme": "scope",
            "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
            "files": []})).json()["data"]["id"]

    async with client(await login("C0002")) as c:
        assert (await c.get("/api/entities/practice",
                            params={"keyword": f"隔离验证团{RUN}"})).json()["data"]["total"] == 0
        assert (await c.get("/api/gpa/list", params={"sid": stu1_id})).status_code == 403
    async with client(coun1) as c:
        assert (await c.get("/api/entities/practice",
                            params={"keyword": f"隔离验证团{RUN}"})).json()["data"]["total"] == 1

    # C0001 触达 C0002 名下学生：名册不可见、详情/教务/删除全部 403
    async with client(coun1) as c:
        assert (await c.get("/api/users/students",
                            params={"keyword": target["uid"]})).json()["data"]["total"] == 0
        assert (await c.get("/api/gpa/list", params={"sid": target["id"]})).status_code == 403
        r_del = await c.delete(f"/api/users/students/{target['id']}")
        assert r_del.status_code == 403 and "管理范围" in r_del.json()["detail"]
        r_imp = (await c.post("/api/entities/practice/import", json={
            "rows": [{"sid": target["uid"], "team": "跨班补录", "type": "自主实践团队",
                      "theme": "x", "sponsor": "x", "startDate": "2026-07-01",
                      "endDate": "2026-07-10"}]})).json()
        assert r_imp["data"]["created"] == 0 and "管理范围" in r_imp["data"]["errors"][0]["message"]

    # C0001 审核 C0002 名下学生的记录 → 403（scope 先于状态机）
    async with client(stu2) as c:
        rid2 = (await c.post("/api/entities/practice", json={
            "team": f"他班申报{RUN}", "type": "自主实践团队", "theme": "scope",
            "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
            "files": []})).json()["data"]["id"]
    async with client(coun1) as c:
        assert (await c.post(f"/api/audit/submit/practice/{rid2}",
                             json={"status": "通过", "opinion": "越权"})).status_code == 403
    # 正向：归属辅导员 C0002 可正常操作
    async with client(await login("C0002")) as c:
        ok = (await c.post(f"/api/audit/submit/practice/{rid2}",
                           json={"status": "驳回", "opinion": "演示清理"})).json()
        assert ok["code"] == 0

    # 清理
    async with client(stu1) as c:
        assert (await c.delete(f"/api/entities/practice/{rid}")).json()["code"] == 0
    async with client(stu2) as c:
        assert (await c.delete(f"/api/entities/practice/{rid2}")).json()["code"] == 0


# ------------------------------------------------- Student：横向越权
async def test_student_cross_user_isolation():
    """学生读/改/删他人记录一律 404（不暴露记录存在性），自己的可正常操作"""
    stu1, stu2 = await login("202300001"), await login("202300002")
    payload = {"team": f"横向隔离{RUN}", "type": "自主实践团队", "theme": "isolation",
               "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
               "files": []}
    async with client(stu1) as c:
        rid = (await c.post("/api/entities/practice", json=payload)).json()["data"]["id"]
    async with client(stu2) as c:
        assert (await c.get(f"/api/entities/practice/{rid}")).status_code == 404
        assert (await c.put(f"/api/entities/practice/{rid}", json=payload)).status_code == 404
        assert (await c.delete(f"/api/entities/practice/{rid}")).status_code == 404
        # 教务成绩：学生只能查自己的（gpa/my），gpa/list 是管理端
        assert (await c.get("/api/gpa/list", params={"sid": rid})).status_code == 403
        mine = (await c.get("/api/gpa/my")).json()["data"]
        for row in mine:   # my 接口只回本人数据（结构性隔离）
            assert row["semester"] is not None
    async with client(stu1) as c:
        assert (await c.get(f"/api/entities/practice/{rid}")).json()["code"] == 0
        assert (await c.delete(f"/api/entities/practice/{rid}")).json()["code"] == 0


# ------------------------------------------------- Dean：全量正向
async def test_dean_full_access():
    dean = await login("D0001")
    async with client(dean) as c:
        # 学生名册跨年级全量可见（C0001 与 C0002 名下都有）
        assert (await c.get("/api/users/students",
                            params={"keyword": "202300001"})).json()["data"]["total"] >= 1
        assert (await c.get("/api/users/students",
                            params={"keyword": "2024", "pageSize": 5})).json()["data"]["total"] >= 1
        # 审核中心（summary 守卫加固后院长仍在白名单）
        summary = (await c.get("/api/audit/summary")).json()
        assert summary["code"] == 0 and "deanPendingTotal" in summary["data"]
        rec = (await c.get("/api/audit/records",
                           params={"key": "practice", "status": "待审核", "pageSize": 5})).json()
        assert rec["code"] == 0 and isinstance(rec["data"]["list"], list)
        # 操作日志 / 异议列表可读
        assert (await c.get("/api/logs", params={"pageSize": 5})).json()["code"] == 0
        assert (await c.get("/api/objections", params={"pageSize": 5})).json()["code"] == 0
