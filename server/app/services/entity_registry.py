"""实体注册表 — 系统的核心抽象

一份注册表同时驱动：
- 后端通用 CRUD/审核路由（参数校验、字段过滤、学分自动计算）
- 前端 EntityPage 泛型组件（表格列、表单、搜索、字典联动）
前后端共用同一份字段契约（前端从 /api/meta/entities 获取，避免两处维护）。
"""
from dataclasses import dataclass, field
from typing import Any

from app.models.database import (Certificate, GpaComp, Honor, Innovation,
                                 Organization, Party, Practice, Voluntary)


@dataclass
class FieldDef:
    name: str
    label: str
    type: str = "text"          # text | textarea | number | date | select | kv
    required: bool = False
    options: str | None = None  # select 的字典 key（meta.py）
    kv_category: str | None = None  # type=kv 时对应的创新类别
    placeholder: str = ""
    in_table: bool = True       # 是否出现在列表
    half: bool = True           # 表单是否半宽


@dataclass
class EntityDef:
    key: str
    model: Any
    label: str
    group: str                  # practice | inn | other
    fields: list[FieldDef] = field(default_factory=list)
    search_fields: list[str] = field(default_factory=list)
    order_by: str = "createdAt"
    dean_review: bool = False   # True=辅导员仅初审，院长终审（高学分/稀缺/易争议类）；False=辅导员直接终审

    @property
    def table_fields(self) -> list[FieldDef]:
        return [f for f in self.fields if f.in_table]

    def form_fields(self, category: str | None = None) -> list[FieldDef]:
        return self.fields

    def validate_payload(self, payload: dict) -> dict:
        """过滤白名单字段 + 必填校验（学分一律由服务端按规则矩阵核定，不接收客户端传值）"""
        data, errors = {}, []
        for f in self.fields:
            if f.type == "kv":
                # kv 字段值由 apply_kv 从两级选择写入，必选校验在 apply_kv 内完成
                continue
            v = payload.get(f.name)
            if f.required and (v is None or str(v).strip() == ""):
                errors.append(f"{f.label}不能为空")
                continue
            if v is None:
                continue
            if f.type == "number":
                v = float(v)
            data[f.name] = v
        return data, errors


ENTITY_REGISTRY: dict[str, EntityDef] = {e.key: e for e in [
    EntityDef(
        key="practice", model=Practice, label="社会实践活动", group="practice",
        search_fields=["team", "theme"],
        fields=[
            FieldDef("team", "实践团队名称", "text", True, placeholder="如：XX学院赴XX地社会实践团"),
            FieldDef("type", "实践类型", "select", True, options="practice_type"),
            FieldDef("theme", "实践主题", "text", True),
            FieldDef("sponsor", "主办单位", "text", True),
            FieldDef("startDate", "开始日期", "date", True),
            FieldDef("endDate", "结束日期", "date", True),
        ]),
    EntityDef(
        key="voluntary", model=Voluntary, label="志愿服务活动", group="practice",
        search_fields=["project", "sponsor"],
        fields=[
            FieldDef("project", "服务项目", "text", True),
            FieldDef("duration", "服务时长(小时)", "number", True),
            FieldDef("sponsor", "组织单位", "text", True),
        ]),
    EntityDef(
        key="inn_chair", model=Innovation, label="前沿学术报告", group="inn",
        search_fields=["project", "implementation"],
        fields=[
            FieldDef("project", "讲座系列", "kv", True, kv_category="chair"),
            FieldDef("implementation", "报告主题/场次", "text", True),
        ]),
    EntityDef(
        key="inn_project", model=Innovation, label="年度创新创业项目", group="inn",
        search_fields=["implementation"],
        fields=[
            FieldDef("implementation", "项目名称", "text", True),
            FieldDef("project", "立项级别", "kv", True, kv_category="project"),
            FieldDef("post", "承担角色", "text", False),
            FieldDef("deadline", "结题时间", "date", False),
        ]),
    EntityDef(
        key="inn_competition", model=Innovation, label="科技创新竞赛", group="inn",
        search_fields=["project"], dean_review=True,
        fields=[
            FieldDef("project", "竞赛名称", "text", True),
            FieldDef("honor", "获奖情况", "kv", True, kv_category="competition"),
            FieldDef("post", "人员次序", "select", False, options="award_post"),
            FieldDef("date", "获奖日期", "date", True),
        ]),
    EntityDef(
        key="inn_enterprise", model=Innovation, label="创业实践", group="inn",
        search_fields=["project"], dean_review=True,
        fields=[
            FieldDef("project", "创业项目名称", "text", True),
            FieldDef("implementation", "创业类型", "kv", True, kv_category="enterprise"),
            FieldDef("post", "承担角色", "select", False, options="award_post"),
            FieldDef("date", "日期", "date", True),
        ]),
    EntityDef(
        key="inn_paper", model=Innovation, label="学术论文", group="inn",
        search_fields=["project"], dean_review=True,
        fields=[
            FieldDef("project", "论文题目", "text", True),
            FieldDef("implementation", "发表情况", "kv", True, kv_category="paper"),
            FieldDef("date", "发表日期", "date", True),
        ]),
    EntityDef(
        key="inn_patent", model=Innovation, label="申请专利", group="inn",
        search_fields=["project"], dean_review=True,
        fields=[
            FieldDef("project", "专利名称", "text", True),
            FieldDef("implementation", "专利类型", "kv", True, kv_category="patent"),
            FieldDef("date", "申请日期", "date", True),
        ]),
    EntityDef(
        key="inn_other", model=Innovation, label="其他实践活动", group="inn",
        search_fields=["project"],
        fields=[
            FieldDef("project", "活动名称", "text", True),
            FieldDef("implementation", "活动类别", "kv", True, kv_category="other"),
            FieldDef("date", "日期", "date", True),
        ]),
    EntityDef(
        key="honor", model=Honor, label="个人荣誉", group="other",
        search_fields=["project", "team"], dean_review=True,
        fields=[
            FieldDef("project", "荣誉名称", "text", True),
            FieldDef("level", "级别", "select", True, options="honor_level"),
            FieldDef("team", "授予单位", "text", False),
            FieldDef("date", "获得日期", "date", True),
        ]),
    EntityDef(
        key="certificate", model=Certificate, label="技能证书", group="other",
        search_fields=["project", "code"],
        fields=[
            FieldDef("project", "证书名称", "text", True),
            FieldDef("code", "证书编号", "text", False),
            FieldDef("date", "获得日期", "date", True),
        ]),
    EntityDef(
        key="organization", model=Organization, label="组织经历", group="other",
        search_fields=["team", "post"],
        fields=[
            FieldDef("team", "组织名称", "text", True),
            FieldDef("type", "组织类型", "cascader", True, options="organ_cascader"),
            FieldDef("post", "担任职务", "text", True),
            FieldDef("startDate", "开始时间", "date", True),
            FieldDef("endDate", "结束时间", "date", True),
        ]),
    EntityDef(
        key="party", model=Party, label="入党情况", group="other",
        search_fields=["type", "department"],
        fields=[
            FieldDef("type", "发展阶段", "select", True, options="party_type"),
            FieldDef("department", "所在党支部", "text", False),
            FieldDef("boss", "入党介绍人", "text", False),
            FieldDef("leader", "培养联系人", "text", False),
            FieldDef("date", "日期", "date", True),
        ]),
]}

# Innovation 实体 key -> category 映射
INN_CATEGORY = {
    "inn_chair": "chair", "inn_project": "project", "inn_competition": "competition",
    "inn_enterprise": "enterprise", "inn_paper": "paper", "inn_patent": "patent",
    "inn_other": "other",
}


def category_scope(key: str, model):
    """Innovation 7 类共用一张表：返回按实体 key 对应 category 的过滤条件（其他实体返回 None）。

    任何按实体 key 遍历注册表做统计/列表的地方都必须套上这个过滤，
    否则 7 个创新板块会互相串数据、计数放大 7 倍。
    """
    if key in INN_CATEGORY:
        return model.category == INN_CATEGORY[key]
    return None


def registry_payload() -> list[dict]:
    """输出给前端的实体契约（/api/meta/entities）"""
    out = []
    for e in ENTITY_REGISTRY.values():
        search = [x for x in e.fields if x.name in e.search_fields] or e.fields[:1]
        out.append({
            "key": e.key, "label": e.label, "group": e.group,
            "deanReview": e.dean_review,
            "searchPlaceholder": " / ".join(f.label for f in search),
            "searchFields": [f.name for f in search],
            "fields": [{
                "name": f.name, "label": f.label, "type": f.type,
                "required": f.required, "options": f.options,
                "kvCategory": f.kv_category, "placeholder": f.placeholder,
                "inTable": f.in_table, "half": f.half,
            } for f in e.fields],
        })
    return out
