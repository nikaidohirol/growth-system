"""locust 压测脚本 — 三角色混合真实负载

启动：
    # 先起后端（默认 8000，使用已灌种的 dev 库）
    .venv/Scripts/python -m uvicorn main:app --port 8000
    # 压测 30s，50 并发，输出 CSV 到 benchmarks/
    .venv/Scripts/python -m locust -f benchmarks/locustfile.py --headless \
        -u 50 -r 10 -t 30s --only-summary --csv benchmarks/result

角色构成按真实系统比例模拟：学生 70% / 辅导员 20% / 院长 10%，
任务权重对应用户高频操作（看板 / 列表检索 / 学分全景）。
"""
import itertools

from locust import HttpUser, between, task

_counter = itertools.count()


class GrowthUser(HttpUser):
    wait_time = between(0.5, 1.5)
    host = "http://localhost:8000"

    def on_start(self):
        idx = next(_counter) % 10
        if idx < 7:                      # 学生 70%
            self.uid = f"20230000{idx + 1}"   # 202300001 ~ 202300007
            self.role = "student"
        elif idx < 9:                    # 辅导员 20%
            self.uid = f"C{idx - 6:04d}"   # C0001 / C0002
            self.role = "counsellor"
        else:                            # 院长 10%
            self.uid = "D0001"
            self.role = "dean"
        r = self.client.post("/api/auth/login",
                             json={"uid": self.uid, "password": "123456"})
        self.token = r.json()["data"]["token"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(3)
    def pandect(self):
        """学生学分全景（双创/实践饼图 + 差额计算，读时计算重接口）"""
        if self.role == "student":
            self.client.get("/api/dashboard/student/pandect")

    @task(2)
    def comp_forecast_me(self):
        """学生综测过程分测算"""
        if self.role == "student":
            self.client.get("/api/dashboard/student/comp-forecast")

    @task(2)
    def entity_list(self):
        """通用实体列表检索（分页 + 排序）"""
        self.client.get("/api/entities/practice", params={"page": 1, "pageSize": 10})

    @task(3)
    def audit_summary(self):
        """审核中心统计（状态分桶计数）"""
        if self.role != "student":
            self.client.get("/api/audit/summary")

    @task(3)
    def counsellor_dashboard(self):
        """辅导员看板（13 实体待审计数）"""
        if self.role == "counsellor":
            self.client.get("/api/dashboard/counsellor")

    @task(2)
    def comp_ranking(self):
        """综测专业排名表（全量学生测算）"""
        if self.role != "student":
            self.client.get("/api/dashboard/comp-forecast")

    @task(4)
    def dean_dashboard(self):
        """院长看板（52 次 count 聚合，缓存命中验证的关键观测点）"""
        if self.role == "dean":
            self.client.get("/api/dashboard/dean")
