"""SQLAlchemy 数据模型

设计要点：
- 单一 User 表承载 Student / Counsellor / Dean 三种角色（RBAC）
- 9 张业务实体表，审核字段（status/auditor/opinion/auditTime）直接内嵌 —— 审核与业务 1:1，
  替代旧系统 13 套 entity + audit 双表接口
- Innovation 用 category 字段承载 7 类双创（chair/project/competition/enterprise/paper/patent/other）
"""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint, select)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def gen_id() -> str:
    return uuid.uuid4().hex


engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
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
    counsellorId: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(64))                   # 辅导员/院长职务


class AuditMixin:
    """内嵌审核字段：学生提交即进入『待审核』，辅导员通过/驳回后回写"""
    status: Mapped[str] = mapped_column(String(16), default="待审核", index=True)  # 待审核/通过/驳回
    auditor: Mapped[str | None] = mapped_column(String(64))
    opinion: Mapped[str | None] = mapped_column(String(255))
    auditTime: Mapped[str | None] = mapped_column(String(32))
    files: Mapped[list | None] = mapped_column(JSON, default=list)  # [{label, url}]
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class Practice(Base, AuditMixin):
    """社会实践活动"""
    __tablename__ = "practices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
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
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    project: Mapped[str] = mapped_column(String(128))
    duration: Mapped[float] = mapped_column(Float)          # 服务时长（小时）
    sponsor: Mapped[str] = mapped_column(String(128))


class Honor(Base, AuditMixin):
    """个人荣誉"""
    __tablename__ = "honors"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    project: Mapped[str] = mapped_column(String(128))       # 荣誉名称
    level: Mapped[str] = mapped_column(String(16))          # 级别
    date: Mapped[str] = mapped_column(String(16))
    team: Mapped[str | None] = mapped_column(String(128))   # 授予单位


class Certificate(Base, AuditMixin):
    """技能证书"""
    __tablename__ = "certificates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    project: Mapped[str] = mapped_column(String(128))       # 证书名称
    code: Mapped[str | None] = mapped_column(String(64))    # 证书编号
    date: Mapped[str] = mapped_column(String(16))


class Organization(Base, AuditMixin):
    """组织经历"""
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    team: Mapped[str] = mapped_column(String(128))          # 组织名称
    type: Mapped[str] = mapped_column(String(32))           # 组织类型
    post: Mapped[str] = mapped_column(String(32))           # 担任职务
    startDate: Mapped[str] = mapped_column(String(16))
    endDate: Mapped[str] = mapped_column(String(16))


class Party(Base, AuditMixin):
    """入党情况"""
    __tablename__ = "parties"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    date: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))           # 阶段
    department: Mapped[str | None] = mapped_column(String(128))  # 党支部
    boss: Mapped[str | None] = mapped_column(String(32))    # 介绍人
    leader: Mapped[str | None] = mapped_column(String(64))  # 培养联系人


class Innovation(Base, AuditMixin):
    """创新创业（category 承载 7 类：chair/project/competition/enterprise/paper/patent/other）"""
    __tablename__ = "innovations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
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
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
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
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    startDate: Mapped[str] = mapped_column(String(16))
    endDate: Mapped[str] = mapped_column(String(16))
    college: Mapped[str] = mapped_column(String(64))
    major: Mapped[str] = mapped_column(String(64))
    classId: Mapped[str | None] = mapped_column(String(32))
    eyewitness: Mapped[str | None] = mapped_column(String(64))  # 见证人


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sid: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(64), default="新对话")
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_id)
    sessionId: Mapped[str] = mapped_column(String(32), ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))           # user / assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON)      # RAG 命中的知识片段
    createdAt: Mapped[str] = mapped_column(String(32), default=lambda: now().strftime("%Y-%m-%d %H:%M:%S"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
