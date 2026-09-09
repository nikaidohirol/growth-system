"""SQLAlchemy 数据模型

设计要点：
- 单一 User 表承载 Student / Counsellor / Dean 三种角色（RBAC）
- 9 张业务实体表，审核字段（status/auditor/opinion/auditTime）直接内嵌 —— 审核与业务 1:1，
  替代旧系统 13 套 entity + audit 双表接口
- Innovation 用 category 字段承载 7 类双创（chair/project/competition/enterprise/paper/patent/other）
"""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Float, ForeignKey, Index, Integer,
                        String, Text)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def gen_id() -> str:
    return uuid.uuid4().hex


# 双驱动：开发默认 SQLite（aiosqlite）；生产 / CI 传 DATABASE_URL=postgresql+asyncpg://... 即切 PostgreSQL
_db_url = settings.DATABASE_URL
_engine_kwargs: dict = {}
if _db_url.startswith("postgresql"):
    # PG 连接池：容器化 / CI 场景下防陈旧连接（SQLite 文件库无需池化参数）
    _engine_kwargs = {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True, "pool_recycle": 1800}
engine = create_async_engine(_db_url, echo=False, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        # 公示期满惰性晋升：每次请求顺带一条 UPDATE（无后台调度器；耗时微秒级，失败不阻断业务）
        try:
            from app.services.audit_flow import promote_expired
            await promote_expired(session)
        except Exception:
            pass
        yield session


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    uid: Mapped[str] = mapped_column(String(32), unique=True, index=True)   # 学号/工号，登录账号
    name: Mapped[str] = mapped_column(String(64))
    passwordHash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), index=True)  # Student / Counsellor / Dean

    # ---- 学生扩展字段（辅导员/院长为 NULL）----
    sex: Mapped[str | None] = mapped_column(String(8))
    nation: Mapped[str | None] = mapped_column(String(16))
    politicsStatus: Mapped[str | None] = mapped_column(String(16))
    birthday: Mapped[str | None] = mapped_column(String(16))
    phone: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(64))
    classId: Mapped[str | None] = mapped_column(String(32), index=True)
    periods: Mapped[str | None] = mapped_column(String(16), index=True)     # 年级，如 2023级
    college: Mapped[str | None] = mapped_column(String(64), index=True)
    major: Mapped[str | None] = mapped_column(String(64))
    origin: Mapped[str | None] = mapped_column(String(64))                  # 生源地
    address: Mapped[str | None] = mapped_column(String(128))
    photo: Mapped[str | None] = mapped_column(String(255))
    counsellorId: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    title: Mapped[str | None] = mapped_column(String(64))                   # 辅导员/院长职务


class AuditMixin:
    """内嵌审核字段：学生提交即进入『待审核』，按审核流状态机流转

    状态机：待审核 →(辅导员通过·院长终审类)→ 待院长审批 →(院长通过)→ 公示中 →(期满惰性)→ 通过
            待审核 →(辅导员通过·日常类)→ 公示中；任意非生效态可驳回，驳回后学生可修改重报
    「通过」恒等于已生效：学分统计、看板等所有 status=='通过' 查询语义自动正确
    """
    @declared_attr
    def __table_args__(cls):
        """复合索引按表名生成，命中两条高频查询模式：
        - (sid, status)：数据权限 scope 过滤 + 状态统计（看板 / 审核中心 / 综测测算）
        - (status, createdAt)：状态筛选 + 倒序排列表格（审核中心列表）
        """
        t = cls.__tablename__
        return (
            Index(f"ix_{t}_sid_status", "sid", "status"),
            Index(f"ix_{t}_status_created", "status", "createdAt"),
        )

    status: Mapped[str] = mapped_column(String(16), default="待审核", index=True)
    auditor: Mapped[str | None] = mapped_column(String(64))
    opinion: Mapped[str | None] = mapped_column(String(255))
    auditTime: Mapped[str | None] = mapped_column(String(32))
    publicEnd: Mapped[str | None] = mapped_column(String(32))   # 公示截止时间（公示中状态使用）
    files: Mapped[list | None] = mapped_column(JSON, default=list)  # [{label, url}]
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class OperationLog(Base):
    """操作日志（合规留痕）

    设计要点：
    - 只增不删不改：不提供任何 update/delete 接口，审计链路不可篡改
    - scope 字段（sid）承载记录归属学生 → 数据权限按角色过滤
    - summary 存人读摘要（字段级 diff / 审核结论），避免前端再做拼装
    """
    __tablename__ = "operation_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    uid: Mapped[str] = mapped_column(String(32), index=True)                # 操作人账号
    operatorName: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))                           # 操作时角色
    action: Mapped[str] = mapped_column(String(16), index=True)             # create/update/delete/audit/login
    entityKey: Mapped[str | None] = mapped_column(String(32), index=True)   # 实体 key（登录为 NULL）
    entityLabel: Mapped[str | None] = mapped_column(String(32))
    recordId: Mapped[str | None] = mapped_column(String(32), index=True)    # 关联记录 id
    sid: Mapped[str | None] = mapped_column(String(32), index=True)         # 记录归属学生（数据权限）
    summary: Mapped[str] = mapped_column(Text)                              # 人读摘要
    createdAt: Mapped[str] = mapped_column(String(32), index=True,
                                           default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class Notification(Base):
    """站内通知（消息触达）

    设计要点：
    - 一份数据，多个渠道：消息本体只存这张表，邮件是异步旁路（未配置 SMTP 自动降级）
    - 私人数据：仅按 uid（学号）查本人，无跨角色查询
    - linkKey/linkId 承载深链：前端点击直达对应记录详情
    """
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    uid: Mapped[str] = mapped_column(String(32), index=True)                # 接收人学号/工号
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(16), default="audit")          # audit / system
    linkKey: Mapped[str | None] = mapped_column(String(32))                 # 实体 key（深链）
    linkId: Mapped[str | None] = mapped_column(String(32))                  # 记录 id
    isRead: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    createdAt: Mapped[str] = mapped_column(String(32), index=True,
                                           default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class Practice(Base, AuditMixin):
    """社会实践活动"""
    __tablename__ = "practices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    team: Mapped[str] = mapped_column(String(128))          # 实践团队名称
    startDate: Mapped[str] = mapped_column(String(16))
    endDate: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))           # 实践类型
    theme: Mapped[str] = mapped_column(String(128))         # 实践主题
    sponsor: Mapped[str] = mapped_column(String(128))       # 主办单位


class Voluntary(Base, AuditMixin):
    """志愿服务活动"""
    __tablename__ = "voluntarys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    project: Mapped[str] = mapped_column(String(128))
    duration: Mapped[float] = mapped_column(Float)          # 服务时长（小时）
    sponsor: Mapped[str] = mapped_column(String(128))


class Honor(Base, AuditMixin):
    """个人荣誉"""
    __tablename__ = "honors"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    project: Mapped[str] = mapped_column(String(128))       # 荣誉名称
    level: Mapped[str] = mapped_column(String(16))          # 级别
    date: Mapped[str] = mapped_column(String(16))
    team: Mapped[str | None] = mapped_column(String(128))   # 授予单位


class Certificate(Base, AuditMixin):
    """技能证书"""
    __tablename__ = "certificates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    project: Mapped[str] = mapped_column(String(128))       # 证书名称
    code: Mapped[str | None] = mapped_column(String(64))    # 证书编号
    date: Mapped[str] = mapped_column(String(16))


class Organization(Base, AuditMixin):
    """组织经历"""
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    team: Mapped[str] = mapped_column(String(128))          # 组织名称
    type: Mapped[str] = mapped_column(String(32))           # 组织类型
    post: Mapped[str] = mapped_column(String(32))           # 担任职务
    startDate: Mapped[str] = mapped_column(String(16))
    endDate: Mapped[str] = mapped_column(String(16))


class Party(Base, AuditMixin):
    """入党情况"""
    __tablename__ = "parties"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    date: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))           # 阶段
    department: Mapped[str | None] = mapped_column(String(128))  # 党支部
    boss: Mapped[str | None] = mapped_column(String(32))    # 介绍人
    leader: Mapped[str | None] = mapped_column(String(64))  # 培养联系人


class Innovation(Base, AuditMixin):
    """创新创业（category 承载 7 类：chair/project/competition/enterprise/paper/patent/other）"""
    __tablename__ = "innovations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    category: Mapped[str] = mapped_column(String(16), index=True)
    project: Mapped[str] = mapped_column(String(128))       # 名称/题目/级别选择
    implementation: Mapped[str | None] = mapped_column(String(255))  # 补充说明（级别/场次等）
    honor: Mapped[str | None] = mapped_column(String(64))   # 获奖情况（competition）
    deadline: Mapped[str | None] = mapped_column(String(16))
    date: Mapped[str | None] = mapped_column(String(16))
    post: Mapped[str | None] = mapped_column(String(32))    # 人员次序
    credit: Mapped[float] = mapped_column(Float, default=0)  # 认定学分（按 KV 规则自动计算）


class GpaComp(Base):
    """综合素质成绩（学期 GPA + 综测）"""
    __tablename__ = "gpa_comps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    semester: Mapped[str] = mapped_column(String(16))
    college: Mapped[str] = mapped_column(String(64))
    major: Mapped[str] = mapped_column(String(64))
    mutual: Mapped[float] = mapped_column(Float)            # 互评成绩
    comp: Mapped[float] = mapped_column(Float)              # 综测成绩
    gpa: Mapped[float] = mapped_column(Float)
    gpaRank: Mapped[int] = mapped_column(Integer)
    compRank: Mapped[int] = mapped_column(Integer)
    maxRank: Mapped[int] = mapped_column(Integer)


class Experience(Base):
    """教育经历（成长档案用）"""
    __tablename__ = "experiences"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    startDate: Mapped[str] = mapped_column(String(16))
    endDate: Mapped[str] = mapped_column(String(16))
    college: Mapped[str] = mapped_column(String(64))
    major: Mapped[str] = mapped_column(String(64))
    classId: Mapped[str | None] = mapped_column(String(32))
    eyewitness: Mapped[str | None] = mapped_column(String(64))  # 见证人


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)
    title: Mapped[str] = mapped_column(String(64), default="新对话")
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sessionId: Mapped[str] = mapped_column(String(32), ForeignKey("chat_sessions.id", deferrable=True, initially="DEFERRED"), index=True)
    role: Mapped[str] = mapped_column(String(16))           # user / assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON)      # RAG 命中的知识片段
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class Objection(Base):
    """公示异议（公示期监督闭环）：实名异议 → 院长复核（成立→记录驳回 / 不成立→维持认定）

    跨实体单表：key + recordId 关联各实体记录；挂着「待复核」异议的公示记录
    暂停惰性晋升（见 audit_flow.promote_expired），杜绝有人异议却自动生效
    """
    __tablename__ = "objections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    key: Mapped[str] = mapped_column(String(32), index=True)        # 实体 key
    recordId: Mapped[str] = mapped_column(String(32), index=True)   # 被异议记录 id
    recordLabel: Mapped[str] = mapped_column(String(32))            # 实体名称（展示冗余）
    recordTitle: Mapped[str] = mapped_column(String(128))           # 认定内容标题（提交时快照）
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", deferrable=True, initially="DEFERRED"), index=True)  # 被异议记录归属学生
    objectorUid: Mapped[str] = mapped_column(String(32))            # 异议人账号（实名）
    objectorName: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)                       # 异议理由（必填）
    status: Mapped[str] = mapped_column(String(16), default="待复核", index=True)
    handledBy: Mapped[str | None] = mapped_column(String(64))       # 复核人
    handledTime: Mapped[str | None] = mapped_column(String(32))
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


def _run_alembic(target: str) -> None:
    """programmatic 跑 Alembic（同步 command）。

    schema 单一事实源 = migrations/（create_all 弃用——PG 严格外键场景下
    两套建表路径容易漂移，迁移链才是可演进的正路）
    """
    from alembic import command
    from alembic.config import Config

    from app.config import BASE_DIR

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    command.upgrade(cfg, target)


async def init_db():
    """建表统一走迁移链；同步命令放线程池避免阻塞事件循环"""
    await asyncio.to_thread(_run_alembic, "head")


async def reset_db():
    """重建库：downgrade 到 base（drop 全部表）再 upgrade head（SEED_RESET=1 触发）"""
    await asyncio.to_thread(_run_alembic, "base")
    await asyncio.to_thread(_run_alembic, "head")
