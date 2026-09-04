"""接口冒烟测试：pytest tests/ -q（需先 python seed.py）"""
import asyncio
import os

os.environ.setdefault("LLM_API_KEY", "")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from main import app  # noqa: E402

TOKENS: dict[str, str] = {}


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
    token = await login("C0001")
    async with client(token) as c:
        summary = (await c.get("/api/audit/summary")).json()["data"]
        assert "pendingTotal" in summary
        records = (await c.get("/api/audit/records",
                               params={"key": "practice", "status": "待审核"})).json()
        assert records["code"] == 0
        if records["data"]["list"]:
            rid = records["data"]["list"][0]["id"]
            ok = (await c.post(f"/api/audit/submit/practice/{rid}",
                               json={"status": "通过", "opinion": "通过"})).json()
            assert ok["code"] == 0
            assert ok["data"]["status"] == "通过"


async def test_dean_dashboard():
    token = await login("D0001")
    async with client(token) as c:
        d = (await c.get("/api/dashboard/dean")).json()["data"]
        assert d["totalStudents"] >= 12
        assert "innByCategory" in d


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test_health())
    print("run with: pytest tests/ -q")
