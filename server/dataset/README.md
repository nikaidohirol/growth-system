# 数据集说明（汽车工程学院 · 演示数据）

由 `server/seed.py` 生成（`python seed.py` 可重建数据库并重新导出，随机种子固定、数据可复现）。

- 规模：院长 1、辅导员 4（C0001~C0004，每级 1 名）、学生 1200（2023~2026 级 × 300 人）
- 演示账号：学生 `202300001`~`202300012`（2023 级车辆 2301 班）· 辅导员 `C0001` · 院长 `D0001`，密码均 `123456`
- 记录分布符合真实业务：高年级记录多、审核通过率高（2023 级约 85%），低年级以「待审核」为主
- 学分取值与 `app/meta.py::INNOVATE_KV` 认定规则一致

| 文件 | 内容 |
| --- | --- |
| students.csv | 学生基本信息（1200 行） |
| staff.csv | 院长 + 辅导员 |
| practices.csv | 社会实践记录 |
| voluntarys.csv | 志愿服务记录 |
| innovations.csv | 创新创业记录（7 类：报告/项目/竞赛/创业/论文/专利/其他） |
| honors.csv | 个人荣誉 |
| certificates.csv | 技能证书 |
| organizations.csv | 组织经历 |
| parties.csv | 入党情况 |
| gpa.csv | 每学期综合成绩（GPA/综测/排名） |
| experiences.csv | 教育经历 |

编码均为 UTF-8 with BOM，Excel 双击可直接打开不乱码。
