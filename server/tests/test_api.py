"""接口冒烟测试：pytest tests/ -q（需先 python seed.py）

覆盖多级审核流：待审核 →(辅导员通过·日常类)→ 公示中 →(期满惰性)→ 通过
                          待审核 →(辅导员通过·终审类)→ 待院长审批 →(院长通过/批量确认)→ 公示中
申报窗口仅约束学生自主申报；辅导员/院长补录不受限。
"""
import asyncio
import base64
import os
import uuid

os.environ.setdefault("LLM_API_KEY", "")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.meta as meta  # noqa: E402
from main import app  # noqa: E402

TOKENS: dict[str, str] = {}
RUN = uuid.uuid4().hex[:6]   # 每次运行唯一后缀：失败残留数据不影响关键字检索断言


@pytest.fixture(autouse=True)
def _open_window(monkeypatch):
    """申报窗口与运行日期解耦：默认强制全开，窗口专项用例内自行改窄"""
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


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health")
        assert r.json()["code"] == 0


async def test_student_flow():
    token = await login("202300001")
    async with client(token) as c:
        me = (await c.get("/api/auth/me")).json()["data"]
        assert me["role"] == "Student"
        pandect = (await c.get("/api/dashboard/student/pandect")).json()["data"]
        assert "innCredit" in pandect and "rules" in pandect
        # 完整 CRUD：创建 -> 列表 -> 更新 -> 删除
        payload = {"team": "测试实践团", "type": "自主实践团队", "theme": "测试主题",
                   "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
                   "files": []}
        created = (await c.post("/api/entities/practice", json=payload)).json()
        assert created["code"] == 0 and created["data"]["status"] == "待审核"
        rid = created["data"]["id"]
        lst = (await c.get("/api/entities/practice", params={"keyword": "测试实践团"})).json()
        assert lst["data"]["total"] >= 1
        payload["theme"] = "测试主题2"
        upd = (await c.put(f"/api/entities/practice/{rid}", json=payload)).json()
        assert upd["code"] == 0
        dele = (await c.delete(f"/api/entities/practice/{rid}")).json()
        assert dele["code"] == 0
        # 离线 chat SSE 不应 5xx
        r = await c.post("/api/ai/chat", json={"message": "社会实践怎么算学分？"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


async def test_counsellor_audit_flow():
    """日常类（practice 无需院长终审）：辅导员通过 → 公示中（非直接生效）"""
    stu, coun = await login("202300001"), await login("C0001")
    # 辅导员补录一条待审核记录（自备数据、可重复运行）
    async with client(coun) as c:
        imp = (await c.post("/api/entities/practice/import", json={
            "rows": [{"sid": "202300001", "team": f"审核流测试团{RUN}", "type": "自主实践团队",
                      "theme": "辅导员终审", "sponsor": "测试学院",
                      "startDate": "2026-07-01", "endDate": "2026-07-10"}]})).json()
        assert imp["code"] == 0 and imp["data"]["created"] == 1, imp
        summary = (await c.get("/api/audit/summary")).json()["data"]
        assert "pendingTotal" in summary and "deanPendingTotal" in summary
        records = (await c.get("/api/audit/records",
                               params={"key": "practice", "status": "待审核",
                                       "keyword": "202300001"})).json()
        assert records["code"] == 0 and records["data"]["list"]
        rid = records["data"]["list"][0]["id"]
        ok = (await c.post(f"/api/audit/submit/practice/{rid}",
                           json={"status": "通过", "opinion": "通过"})).json()
        assert ok["code"] == 0
        assert ok["data"]["status"] == "公示中"          # 日常类通过后进入公示期
        assert ok["data"]["publicEnd"]                  # 公示截止时间已设置
        # 公示中记录辅导员不可再操作（仅院长可纠错驳回）
        rej = await c.post(f"/api/audit/submit/practice/{rid}",
                           json={"status": "驳回", "opinion": "演示清理"})
        assert rej.status_code == 403
    async with client(stu) as c:
        got = (await c.get(f"/api/entities/practice/{rid}")).json()["data"]
        assert got["status"] == "公示中"
        assert (await c.delete(f"/api/entities/practice/{rid}")).status_code == 400  # 公示中锁定
    async with client(await login("D0001")) as c:
        back = (await c.post(f"/api/audit/submit/practice/{rid}",
                             json={"status": "驳回", "opinion": "演示清理"})).json()
        assert back["code"] == 0 and back["data"]["status"] == "驳回"  # 公示异议驳回


async def test_dean_review_flow():
    """终审类（inn_competition dean_review）：初审→待院长审批→终审/批量确认→公示→惰性生效"""
    from sqlalchemy import update as sa_update

    from app.models.database import AsyncSessionLocal, Innovation

    stu, coun, dean = await login("202300001"), await login("C0001"), await login("D0001")
    payload = {"project": "分级流转竞赛", "post": "第一完成人", "date": "2026-07-01",
               "_kv_chiefly": "省级", "_kv_minor": "一等奖", "files": []}
    async with client(stu) as c:
        rid = (await c.post("/api/entities/inn_competition", json=payload)).json()["data"]["id"]
    # 辅导员初审通过 → 待院长审批（不生效、不进公示）
    async with client(coun) as c:
        ok = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                           json={"status": "通过", "opinion": "初审通过"})).json()
        assert ok["code"] == 0 and ok["data"]["status"] == "待院长审批"
        assert ok["data"]["auditor"] == "李文静" and ok["data"]["publicEnd"] is None
        # 已进入院长环节，辅导员不可再操作
        again = await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "通过", "opinion": "x"})
        assert again.status_code == 400
    # 学生不可修改/删除锁定态记录
    async with client(stu) as c:
        assert (await c.put(f"/api/entities/inn_competition/{rid}", json=payload)).status_code == 400
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).status_code == 400
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["credit"] == 3.0        # 申报时已核定，但尚未正式生效
    # 院长单条终审权 + 批量确认（含无效 id 跳过）
    async with client(dean) as c:
        summary = (await c.get("/api/audit/summary")).json()["data"]
        assert summary["deanPendingTotal"] >= 1
        batch = (await c.post("/api/audit/batch/inn_competition",
                              json={"ids": [rid, "nonexistent-id"]})).json()
        assert batch["code"] == 0
        assert batch["data"] == {"confirmed": 1, "skipped": 1}
    async with client(stu) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["status"] == "公示中" and got["publicEnd"]
        assert got["auditor"] == "王建国"           # 终审留痕
        assert got["credit"] == 3.0                 # 生效前按矩阵正式核定
    # 院长对公示中记录重复通过 → 400；辅导员操作 → 403
    async with client(dean) as c:
        dup = await c.post(f"/api/audit/submit/inn_competition/{rid}",
                           json={"status": "通过", "opinion": "x"})
        assert dup.status_code == 400
    async with client(coun) as c:
        forbidden = await c.post(f"/api/audit/submit/inn_competition/{rid}",
                                 json={"status": "驳回", "opinion": "x"})
        assert forbidden.status_code == 403
    # 公示期满惰性晋升：回拨 publicEnd → 任意请求顺带晋升为「通过」
    async with AsyncSessionLocal() as s:
        await s.execute(sa_update(Innovation).where(Innovation.id == rid)
                        .values(publicEnd="2000-01-01 00:00:00"))
        await s.commit()
    async with client(stu) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["status"] == "通过"              # 已生效
        assert (await c.put(f"/api/entities/inn_competition/{rid}", json=payload)).status_code == 400
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).status_code == 400
    # 清理：院长纠错驳回 → 学生可删除
    async with client(dean) as c:
        back = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "驳回", "opinion": "演示清理"})).json()
        assert back["code"] == 0
        await c.post("/api/notifications/read", json={"all": True})
    async with client(stu) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0


async def test_apply_window():
    """申报窗口：窗口外学生自主申报被拦（400），辅导员按学号补录不受限"""
    monkey_closed = pytest.MonkeyPatch()
    monkey_closed.setitem(meta.AUDIT_FLOW, "windowStart", "2000-01-01")
    monkey_closed.setitem(meta.AUDIT_FLOW, "windowEnd", "2000-01-02")
    try:
        stu, coun = await login("202300001"), await login("C0001")
        payload = {"project": "窗口外竞赛", "post": "第一完成人", "date": "2026-07-01",
                   "_kv_chiefly": "省级", "_kv_minor": "一等奖", "files": []}
        async with client(stu) as c:
            r = (await c.post("/api/entities/inn_competition", json=payload))
            assert r.status_code == 400 and "申报窗口" in r.json()["detail"]
        # 辅导员 Excel 补录（历史数据迁移通道）不受窗口限制
        async with client(coun) as c:
            imp = (await c.post("/api/entities/inn_competition/import", json={
                "rows": [dict(payload, sid="202300001", project=f"窗口外补录{RUN}")]})).json()
            assert imp["code"] == 0 and imp["data"]["created"] == 1, imp
            lst = (await c.get("/api/entities/inn_competition",
                               params={"keyword": f"窗口外补录{RUN}"})).json()["data"]["list"]
            assert lst[0]["status"] == "待审核"
            rid = lst[0]["id"]
            assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0
    finally:
        monkey_closed.undo()


async def test_dean_dashboard():
    token = await login("D0001")
    async with client(token) as c:
        d = (await c.get("/api/dashboard/dean")).json()["data"]
        assert d["totalStudents"] >= 1000  # 汽车工程学院规模数据集（1200 学生）
        assert "innByCategory" in d
        assert "deanPendingTotal" in d and "publicTotal" in d
        assert isinstance(d["counsellorStats"], list) and len(d["counsellorStats"]) >= 1
        assert all({"name", "total", "passed", "rate"} <= set(s) for s in d["counsellorStats"])


# 1x1 PNG（base64），用于上传/多模态测试
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


async def test_gpa_api():
    stu = await login("202300001")
    async with client(stu) as c:
        me = (await c.get("/api/auth/me")).json()["data"]
        r = await c.get("/api/gpa/my")  # GPA 接口已挂载，不再是 404
        assert r.status_code == 200 and r.json()["code"] == 0
        assert isinstance(r.json()["data"], list)
    token = await login("C0001")
    async with client(token) as c:
        lst = (await c.get("/api/gpa/list", params={"sid": me["id"]})).json()
        assert lst["code"] == 0
        before = len(lst["data"])
        payload = {"sid": me["id"], "semester": "9999-9", "college": "测试学院",
                   "major": "测试专业", "mutual": 80.0, "comp": 85.0, "gpa": 3.5,
                   "gpaRank": 1, "compRank": 2, "maxRank": 30}
        assert (await c.post("/api/gpa", json=payload)).json()["code"] == 0
        rows = (await c.get("/api/gpa/list", params={"sid": me["id"]})).json()["data"]
        assert len(rows) == before + 1
        row_id = next(x["id"] for x in rows if x["semester"] == "9999-9")
        assert (await c.delete(f"/api/gpa/{row_id}")).json()["code"] == 0
        rows = (await c.get("/api/gpa/list", params={"sid": me["id"]})).json()["data"]
        assert len(rows) == before


async def test_multimodal_chat():
    token = await login("202300001")
    async with client(token) as c:
        up = (await c.post("/api/files/upload",
                           files=[("files", ("a.png", PNG_BYTES, "image/png"))])).json()
        assert up["code"] == 0, up
        url = up["data"][0]["url"]
        assert url.startswith("/files/")
        # 单元级：图片 URL → base64 data URL 多模态消息；越界路径被跳过
        from app.routers.ai import _build_multimodal_message
        msg = _build_multimodal_message("看图", [url, "/files/../../app/config.py"])
        assert len(msg.content) == 2  # 恶意路径被过滤，只剩 1 图 + 1 文本
        assert msg.content[0]["type"] == "image_url"
        assert msg.content[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert msg.content[1] == {"type": "text", "text": "看图"}
        # 集成级：带图片的 SSE 对话正常出流（离线模式含降级提示）
        r = await c.post("/api/ai/chat", json={"message": "图片里是什么？", "images": [url]})
        assert r.status_code == 200
        assert "event: meta" in r.text and "event: done" in r.text


async def test_reject_resubmit_resets_status():
    stu, coun = await login("202300001"), await login("C0001")
    payload = {"team": "驳回测试团", "type": "自主实践团队", "theme": "驳回重报",
               "sponsor": "测试学院", "startDate": "2026-07-01", "endDate": "2026-07-10",
               "files": []}
    async with client(stu) as c:
        created = (await c.post("/api/entities/practice", json=payload)).json()
        assert created["code"] == 0
        rid = created["data"]["id"]
    async with client(coun) as c:
        rej = (await c.post(f"/api/audit/submit/practice/{rid}",
                            json={"status": "驳回", "opinion": "材料不全"})).json()
        assert rej["code"] == 0 and rej["data"]["status"] == "驳回"
    async with client(stu) as c:
        upd = (await c.put(f"/api/entities/practice/{rid}", json=payload)).json()
        assert upd["code"] == 0
        assert upd["data"]["status"] == "待审核"      # 重报自动回到待审核
        assert upd["data"]["auditor"] is None and upd["data"]["opinion"] is None
        assert (await c.delete(f"/api/entities/practice/{rid}")).json()["code"] == 0


async def test_credit_rule_matrix():
    """规则矩阵核定：创建即服务端核定（含竞赛次序折算）、_credit 注入无效、
    终审类通过需院长终审，正式核定在进入公示时执行"""
    from app.services.credits import assess_inn_credit
    # 纯函数级：基准分 × 次序系数
    assert assess_inn_credit("competition", "国家级", "一等奖", "第一完成人") == 6.0
    assert assess_inn_credit("competition", "国家级", "一等奖", "第二完成人") == 4.2
    assert assess_inn_credit("competition", "国家级", "一等奖", "其他成员") == 1.8
    assert assess_inn_credit("competition", "国家级", "一等奖") == 6.0      # 无次序不折算
    assert assess_inn_credit("paper", "SCI/EI 收录", "第一作者") == 6.0     # 无次序系数类
    assert assess_inn_credit("competition", "国家级", "特等奖") is None    # 无效组合
    # 接口级：学生申报 → 服务端核定，客户端 _credit 注入被忽略
    stu, coun, dean = await login("202300001"), await login("C0001"), await login("D0001")
    payload = {"project": "核定测试竞赛", "post": "第二完成人", "date": "2026-07-01",
               "_kv_chiefly": "国家级", "_kv_minor": "一等奖", "_credit": 99, "files": []}
    async with client(stu) as c:
        created = (await c.post("/api/entities/inn_competition", json=payload)).json()
        assert created["code"] == 0, created
        assert created["data"]["credit"] == 4.2   # 6 × 0.7，而非客户端注入的 99
        assert created["data"]["honor"] == "国家级·一等奖"
        rid = created["data"]["id"]
    # 辅导员初审通过 → 待院长审批（终审类不直接生效）
    async with client(coun) as c:
        ok = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                           json={"status": "通过", "opinion": "核定通过"})).json()
        assert ok["code"] == 0
        assert ok["data"]["status"] == "待院长审批"
        # 院长环节辅导员驳回 → 400
        guard = await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "驳回", "opinion": "x"})
        assert guard.status_code == 400
    # 院长终审通过 → 进入公示，服务端按矩阵重算学分（不沿用自报值）
    async with client(dean) as c:
        ok = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                           json={"status": "通过", "opinion": "终审通过"})).json()
        assert ok["code"] == 0
        assert ok["data"]["status"] == "公示中"
        assert ok["data"]["credit"] == 4.2
        assert ok["data"]["auditor"] == "王建国"
        # 纠错驳回后允许删除（已生效/公示中记录学生不可删）
        back = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "驳回", "opinion": "演示清理"})).json()
        assert back["code"] == 0
    async with client(stu) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0


async def test_operation_logs():
    """操作日志：增删改审全埋点 + 数据权限隔离（终审类初审通过留痕为「初审通过…转院长审批」）"""
    stu1, stu2, coun, dean = (await login("202300001"), await login("202300002"),
                              await login("C0001"), await login("D0001"))
    payload = {"project": "日志验证竞赛", "post": "第一完成人", "date": "2026-08-02",
               "_kv_chiefly": "省级", "_kv_minor": "二等奖", "files": []}
    # 学生申报 → 申报日志
    async with client(stu1) as c:
        created = (await c.post("/api/entities/inn_competition", json=payload)).json()["data"]
        rid = created["id"]
        logs = (await c.get(f"/api/logs/record/inn_competition/{rid}")).json()["data"]
        assert any(l["action"] == "create" and "申报科技创新竞赛" in l["summary"] for l in logs)
    # 辅导员初审通过 → 留痕「初审通过…转院长审批」
    async with client(coun) as c:
        ok = (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                           json={"status": "通过", "opinion": "属实"})).json()
        assert ok["code"] == 0
        rec_logs = (await c.get(f"/api/logs/record/inn_competition/{rid}")).json()["data"]
        assert any(l["action"] == "audit" and "初审通过" in l["summary"] for l in rec_logs)
    # 学生视角：查别人记录日志为空（数据权限）；学生不能进管理端日志检索
    async with client(stu2) as c:
        other = (await c.get(f"/api/logs/record/inn_competition/{rid}")).json()["data"]
        assert other == []
        assert (await c.get("/api/logs")).status_code == 403
    # 辅导员管理端日志检索：有审核动作、范围限名下学生
    async with client(coun) as c:
        page = (await c.get("/api/logs", params={"action": "audit", "pageSize": 5})).json()["data"]
        assert page["total"] > 0 and all(l["action"] == "audit" for l in page["list"])
    # 清理：院长驳回（辅导员不可操作院长环节）→ 删除留痕
    async with client(dean) as c:
        await c.post(f"/api/audit/submit/inn_competition/{rid}",
                     json={"status": "驳回", "opinion": "演示清理"})
        await c.post("/api/notifications/read", json={"all": True})
    async with client(stu1) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0
        logs = (await c.get(f"/api/logs/record/inn_competition/{rid}")).json()["data"]
        assert any(l["action"] == "delete" for l in logs)


async def test_excel_import():
    """Excel 批量导入：学生实体导入（服务端核定学分+逐行报错）、辅导员按学号补录（直接通过、不走公示）、
    学生批量导入（字典防呆+留痕）、综合成绩批量导入（重复学期跳过）"""
    stu, coun, dean = await login("202300001"), await login("C0001"), await login("D0001")
    # 1) 学生批量导入本人竞赛记录：有效行核定学分，无效 kv 组合逐行报错不阻断
    rows = [
        {"project": f"导入竞赛A{RUN}", "date": "2026-07-05", "post": "第一完成人",
         "_kv_chiefly": "省级", "_kv_minor": "一等奖"},
        {"project": f"导入竞赛B{RUN}", "date": "2026/07/06", "_kv_chiefly": "国家级", "_kv_minor": "特等奖"},
    ]
    async with client(stu) as c:
        r = (await c.post("/api/entities/inn_competition/import", json={"rows": rows})).json()
        assert r["code"] == 0, r
        assert r["data"]["created"] == 1 and len(r["data"]["errors"]) == 1
        assert "无效的认定组合" in r["data"]["errors"][0]["message"]
        lst = (await c.get("/api/entities/inn_competition",
                           params={"keyword": f"导入竞赛A{RUN}"})).json()
        assert lst["data"]["total"] == 1
        row = lst["data"]["list"][0]
        assert row["status"] == "待审核" and row["credit"] == 3.0   # 省级一等奖 × 第一完成人 1.0
        assert row["date"] == "2026-07-05"
        rid = row["id"]
    # 2) 辅导员按学号补录历史数据（直接通过 + 核定学分 + 补录人留痕，不走公示期）
    async with client(coun) as c:
        r = (await c.post("/api/entities/inn_competition/import", json={
            "status": "通过",
            "rows": [{"sid": "202300001", "project": f"导入竞赛C{RUN}", "date": "2026-07-07",
                      "_kv_chiefly": "校级", "_kv_minor": "二等奖"}]})).json()
        assert r["code"] == 0 and r["data"]["created"] == 1, r
    async with client(stu) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["status"] == "待审核"      # 学生导入的仍是待审核
        lst = (await c.get("/api/entities/inn_competition",
                           params={"keyword": f"导入竞赛C{RUN}"})).json()
        rid2 = lst["data"]["list"][0]["id"]
        assert lst["data"]["list"][0]["status"] == "通过"   # 辅导员补录直接通过（历史迁移通道）
        assert lst["data"]["list"][0]["publicEnd"] is None
    # 清理：待审核直接删；已通过的转驳回后删（辅导员不可纠错已生效记录，需院长）
    async with client(coun) as c:
        guard = await c.post(f"/api/audit/submit/inn_competition/{rid2}",
                             json={"status": "驳回", "opinion": "演示清理"})
        assert guard.status_code == 403   # 已生效记录仅院长可纠错驳回
    async with client(dean) as c:
        await c.post(f"/api/audit/submit/inn_competition/{rid2}",
                     json={"status": "驳回", "opinion": "演示清理"})
    async with client(stu) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0
        assert (await c.delete(f"/api/entities/inn_competition/{rid2}")).json()["code"] == 0
    # 3) 学生批量导入：字典防呆（年级/学院/专业）+ 去重跳过 + 院长可查批量导入日志
    async with client(coun) as c:
        r = (await c.post("/api/users/students", json=[
            {"uid": "29990001", "name": "导入学生甲", "sex": "男", "classId": "车辆2301班",
             "periods": "2023", "college": "汽车工程学院", "major": "车辆工程"},
            {"uid": "29990001", "name": "重复学生"}])).json()
        assert r["code"] == 0
        assert r["data"]["created"] == ["29990001"] and r["data"]["skipped"] == ["29990001"]
        r2 = (await c.post("/api/users/students", json=[
            {"uid": "29990002", "name": "导入学生乙", "periods": "1998"}])).json()
        assert r2["data"]["created"] == [] and "年级" in r2["data"]["errors"][0]["message"]
        lst = (await c.get("/api/users/students", params={"keyword": "29990001"})).json()
        assert (await c.delete(f"/api/users/students/{lst['data']['list'][0]['id']}")).json()["code"] == 0
    async with client(dean) as c:
        page = (await c.get("/api/logs", params={"keyword": "批量导入学生", "pageSize": 10})).json()
        assert page["data"]["total"] >= 1
    # 4) 综合成绩批量导入：成功 + 重复学期跳过 + 学号不存在报错
    async with client(coun) as c:
        me_id = (await c.get("/api/users/students", params={"keyword": "202300001"})).json()
        sid = me_id["data"]["list"][0]["id"]
        gpa_rows = [{"uid": "202300001", "semester": "8888-1", "mutual": 80, "comp": 85,
                     "gpa": 3.6, "gpaRank": 3, "compRank": 5, "maxRank": 300},
                    {"uid": "99999999", "semester": "8888-1", "mutual": 80, "comp": 85,
                     "gpa": 3.6, "gpaRank": 3, "compRank": 5, "maxRank": 300}]
        r = (await c.post("/api/gpa/import", json={"rows": gpa_rows})).json()
        assert r["code"] == 0 and r["data"]["created"] == 1 and len(r["data"]["errors"]) == 1
        r2 = (await c.post("/api/gpa/import", json={"rows": [gpa_rows[0]]})).json()
        assert r2["data"]["created"] == 0 and "已存在" in r2["data"]["errors"][0]["message"]
        lst = (await c.get("/api/gpa/list", params={"sid": sid})).json()["data"]
        gid = next(x["id"] for x in lst if x["semester"] == "8888-1")
        assert (await c.delete(f"/api/gpa/{gid}")).json()["code"] == 0


async def test_notification():
    """站内通知：分级流转全链路触达——驳回触达学生、重报触达辅导员、初审通过触达院长、
    终审通过（含核定学分）触达学生"""
    stu, coun, dean = await login("202300001"), await login("C0001"), await login("D0001")
    # 先清空三方未读，保证断言不受存量数据影响
    for t in (stu, coun, dean):
        async with client(t) as c:
            await c.post("/api/notifications/read", json={"all": True})
    payload = {"project": "通知验证竞赛", "post": "第一完成人", "date": "2026-08-03",
               "_kv_chiefly": "省级", "_kv_minor": "一等奖", "files": []}
    async with client(stu) as c:
        rid = (await c.post("/api/entities/inn_competition", json=payload)).json()["data"]["id"]
    # 辅导员驳回 → 学生收未读通知（含驳回原因 + 深链）
    async with client(coun) as c:
        assert (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "驳回", "opinion": "证书照片模糊"})).json()["code"] == 0
    async with client(stu) as c:
        box = (await c.get("/api/notifications")).json()["data"]
        assert box["unread"] >= 1
        first = box["list"][0]
        assert "被驳回" in first["title"] and "证书照片模糊" in first["content"]
        assert first["linkKey"] == "inn_competition" and first["linkId"] == rid
        assert first["isRead"] is False
        # 单条已读 → 未读数减一
        await c.post("/api/notifications/read", json={"ids": [first["id"]]})
        after = (await c.get("/api/notifications/unread")).json()["data"]["unread"]
        assert after == box["unread"] - 1
        # 驳回重报 → 辅导员收复审通知
        await c.put(f"/api/entities/inn_competition/{rid}", json=payload)
    async with client(coun) as c:
        box = (await c.get("/api/notifications", params={"unread": "true"})).json()["data"]
        assert box["unread"] >= 1 and any("重新提交" in n["title"] for n in box["list"])
        # 初审通过 → 院长收终审提醒（而非学生收通过通知）
        assert (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "通过", "opinion": "属实"})).json()["code"] == 0
    async with client(dean) as c:
        box = (await c.get("/api/notifications", params={"unread": "true"})).json()["data"]
        assert any("待您院长审批" in n["title"] for n in box["list"])
        # 院长终审通过 → 学生收进入公示期通知（含核定学分 3.0）
        assert (await c.post(f"/api/audit/submit/inn_competition/{rid}",
                             json={"status": "通过", "opinion": "终审通过"})).json()["code"] == 0
    async with client(stu) as c:
        box = (await c.get("/api/notifications")).json()["data"]
        passed = next(n for n in box["list"] if "进入公示期" in n["title"])
        assert "核定学分 3" in passed["content"]
    # 清理：公示异议驳回后删除；生成的通知一并清掉
    async with client(dean) as c:
        await c.post(f"/api/audit/submit/inn_competition/{rid}",
                     json={"status": "驳回", "opinion": "演示清理"})
        await c.post("/api/notifications/read", json={"all": True})
    async with client(stu) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0
        await c.post("/api/notifications/read", json={"all": True})
    async with client(coun) as c:
        await c.post("/api/notifications/read", json={"all": True})


async def test_publicity_objection_flow():
    """公示监督闭环：公示栏聚合 → 实名异议（本人不可异议自己 / 防重复）→ 待复核异议锁定惰性晋升
    → 院长复核（不成立→维持并自动生效 / 成立→记录驳回撤销认定），双向通知触达"""
    from sqlalchemy import update as sa_update

    from app.models.database import AsyncSessionLocal, Innovation

    stu1, stu2, coun, dean = (await login("202300001"), await login("202300002"),
                              await login("C0001"), await login("D0001"))
    payload = {"project": "公示异议竞赛", "post": "第一完成人", "date": "2026-07-01",
               "_kv_chiefly": "省级", "_kv_minor": "二等奖", "files": []}

    async def to_public(project: str) -> str:
        """学生申报 → 辅导员初审 → 院长终审 → 公示中，返回记录 id"""
        created = await c_post(stu1, "/api/entities/inn_competition",
                               dict(payload, project=project))
        rid = created["id"]
        await c_post(coun, f"/api/audit/submit/inn_competition/{rid}",
                     {"status": "通过", "opinion": "初审通过"})
        ok = await c_post(dean, f"/api/audit/submit/inn_competition/{rid}",
                          {"status": "通过", "opinion": "终审通过"})
        assert ok["status"] == "公示中", ok
        return rid

    async def c_post(token: str, url: str, body: dict) -> dict:
        async with client(token) as c:
            r = await c.post(url, json=body)
            assert r.status_code == 200, r.text
            return r.json()["data"]

    rid = await to_public(f"公示异议A{RUN}")
    # 公示栏登录即可见；本人不可对自己的记录提异议
    async with client(stu1) as c:
        board = (await c.get("/api/objections/publicity")).json()["data"]["list"]
        assert any(x["recordId"] == rid for x in board)
        own = await c.post("/api/objections", json={
            "key": "inn_competition", "recordId": rid, "reason": "尝试异议自己的认定记录数据"})
        assert own.status_code == 400 and "辅导员" in own.json()["detail"]
    # 他人实名异议成功；同一记录未复核期间防重复
    async with client(stu2) as c:
        ok1 = (await c.post("/api/objections", json={
            "key": "inn_competition", "recordId": rid,
            "reason": "获奖级别与公示材料不一致，请学院核实"})).json()
        assert ok1["code"] == 0
        dup = await c.post("/api/objections", json={
            "key": "inn_competition", "recordId": rid, "reason": "重复提交的异议理由测试数据"})
        assert dup.status_code == 400 and "已提交过" in dup.json()["detail"]
        mine = (await c.get("/api/objections/mine")).json()["data"]["list"]
        assert mine and mine[0]["status"] == "待复核"
        oid = mine[0]["id"]
    # 待复核异议锁定惰性晋升：回拨 publicEnd 后仍不生效
    async with AsyncSessionLocal() as s:
        await s.execute(sa_update(Innovation).where(Innovation.id == rid)
                        .values(publicEnd="2000-01-01 00:00:00"))
        await s.commit()
    async with client(stu1) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["status"] == "公示中"          # 未复核异议 → 暂停自动生效
    # 学生无异议列表权限；辅导员不可复核；院长复核「不成立」→ 维持认定
    async with client(stu1) as c:
        assert (await c.get("/api/objections")).status_code == 403
    async with client(coun) as c:
        assert (await c.post(f"/api/objections/{oid}/review", json={"result": "不成立"})).status_code == 403
    async with client(dean) as c:
        lst = (await c.get("/api/objections", params={"status": "待复核"})).json()["data"]["list"]
        assert any(x["id"] == oid for x in lst)
        rv = (await c.post(f"/api/objections/{oid}/review",
                           json={"result": "不成立", "opinion": "材料核实无误"})).json()
        assert rv["code"] == 0
        again = await c.post(f"/api/objections/{oid}/review", json={"result": "成立"})
        assert again.status_code == 400 and "已复核" in again.json()["detail"]
    # 解锁后再次访问即惰性晋升为「通过」；异议人收到复核结果通知
    async with client(stu1) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid}")).json()["data"]
        assert got["status"] == "通过"
    async with client(stu2) as c:
        box = (await c.get("/api/notifications")).json()["data"]
        assert any("公示异议已复核：不成立" in n["title"] for n in box["list"])
        await c.post("/api/notifications/read", json={"all": True})
    # 第二条异议 → 复核「成立」→ 记录驳回撤销认定，被异议学生收驳回通知（含异议理由）
    rid2 = await to_public(f"公示异议B{RUN}")
    async with client(stu2) as c:
        assert (await c.post("/api/objections", json={
            "key": "inn_competition", "recordId": rid2,
            "reason": "该记录学分折算有误，次序系数未按规则执行"})).json()["code"] == 0
    async with client(dean) as c:
        lst = (await c.get("/api/objections", params={"status": "待复核"})).json()["data"]["list"]
        oid2 = next(x["id"] for x in lst if x["recordId"] == rid2)
        rv = (await c.post(f"/api/objections/{oid2}/review", json={"result": "成立"})).json()
        assert rv["code"] == 0
    async with client(stu1) as c:
        got = (await c.get(f"/api/entities/inn_competition/{rid2}")).json()["data"]
        assert got["status"] == "驳回" and "公示异议成立" in (got["opinion"] or "")
        box = (await c.get("/api/notifications", params={"unread": "true"})).json()["data"]
        assert any("被驳回" in n["title"] and "公示期收到异议" in n["content"] for n in box["list"])
    # 清理：rid 已惰性晋升为「通过」，需院长纠错驳回后学生才能删除
    async with client(dean) as c:
        await c.post(f"/api/audit/submit/inn_competition/{rid}",
                     json={"status": "驳回", "opinion": "演示清理"})
    async with client(stu1) as c:
        assert (await c.delete(f"/api/entities/inn_competition/{rid}")).json()["code"] == 0
        assert (await c.delete(f"/api/entities/inn_competition/{rid2}")).json()["code"] == 0
    for t in (stu2, dean):
        async with client(t) as c:
            await c.post("/api/notifications/read", json={"all": True})


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test_health())
    print("run with: pytest tests/ -q")
