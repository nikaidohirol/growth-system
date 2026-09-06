"""LangGraph ReAct Agent — 工具调用 + 会话记忆（MemorySaver checkpointer）

- 工具：知识库检索(RAG) / 查询个人学分 / 查询个人记录 / 查待审事项
- 记忆：MemorySaver 按 thread_id=session_id 持久会话状态，进程重启后由 DB 消息回放恢复
- 未配置 LLM Key 时由路由层降级为离线知识库模式，不经过 Agent
"""
import asyncio
from typing import Annotated

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from sqlalchemy import select

from app.meta import CREDIT_RULES, INNOVATE_KV
from app.models.database import Innovation, User, Voluntary
from app.models.database import Practice as PracticeModel
from app.services.credits import compute_pandect
from app.services.entity_registry import ENTITY_REGISTRY
from app.services.llm import get_chat_model
from app.services.rag import search_knowledge

_checkpointer = MemorySaver()


def _ctx(config: RunnableConfig):
    c = config.get("configurable", {})
    return c.get("db"), c.get("user")


@tool
def search_school_knowledge(query: str) -> str:
    """检索学校学分认定规则、系统使用指南等知识库内容。当用户询问政策、规则、流程、怎么办理时调用。"""
    hits = search_knowledge(query, k=4)
    if not hits:
        return "知识库中没有找到相关内容。"
    return "\n\n".join(f"[{h['source']}|{h['title']}]\n{h['content']}" for h in hits)


@tool
async def query_my_credits(config: RunnableConfig) -> str:
    """查询当前学生的创新创业学分、社会实践学分、总学分及距毕业要求的差额。"""
    db, user = _ctx(config)
    if db is None or user is None:
        return "无法获取用户上下文"
    p = await compute_pandect(db, user.id)
    r = p["rules"]
    return (f"创新创业学分 {p['innCredit']}/{r['min_inn']}，"
            f"社会实践学分 {p['praCredit']}/{r['min_pra']}，"
            f"总学分 {p['sumCredit']}/{r['min_sum']}。"
            f"分项：{p['innCreditList']} + {p['practiceCreditList']}。"
            f"社会实践通过 {p['practiceCount']} 次，志愿服务累计 {p['voluntaryHours']} 小时。")


@tool
async def query_my_records(entity_key: str, config: RunnableConfig) -> str:
    """查询当前学生某类记录的近况（状态统计与最近几条）。entity_key 取值：practice/voluntary/inn_chair/inn_project/inn_competition/inn_enterprise/inn_paper/inn_patent/inn_other/honor/certificate/organization/party"""
    db, user = _ctx(config)
    if db is None or user is None:
        return "无法获取用户上下文"
    e = ENTITY_REGISTRY.get(entity_key)
    if e is None:
        return f"未知实体类型 {entity_key}"
    rows = (await db.execute(select(e.model).where(e.model.sid == user.id)
                             .order_by(e.model.createdAt.desc()).limit(20))).scalars().all()
    if not rows:
        return f"暂无【{e.label}】记录。"
    stat: dict[str, int] = {}
    for r in rows:
        stat[r.status] = stat.get(r.status, 0) + 1
    lines = [f"{getattr(r, e.fields[0].name, '')}（{r.status}）" for r in rows[:5]]
    return f"【{e.label}】共 {len(rows)} 条，状态分布 {stat}，最近记录：{'；'.join(lines)}"


@tool
async def query_pending_audits(config: RunnableConfig) -> str:
    """（辅导员/院长）查询名下学生待审核事项汇总。"""
    db, user = _ctx(config)
    if db is None or user is None:
        return "无法获取用户上下文"
    out = []
    for key, e in ENTITY_REGISTRY.items():
        q = select(e.model).where(e.model.status == "待审核")
        if user.role != "Dean":
            sids = select(User.id).where(User.counsellorId == user.id)
            q = q.where(e.model.sid.in_(sids))
        rows = (await db.execute(q.limit(50))).scalars().all()
        if rows:
            out.append(f"{e.label} {len(rows)} 条")
    return "待审核事项：" + ("、".join(out) if out else "无")


TOOLS = [search_school_knowledge, query_my_credits, query_my_records, query_pending_audits]

SYSTEM_PROMPT = """你是『AI 学生成长发展系统』的智能助手，服务对象可能是学生、辅导员或院长。
职责：
1. 解答学分认定规则、审核流程、系统使用问题（优先调用 search_school_knowledge 工具，引用知识库原文）；
2. 学生询问自身学分/记录时调用对应查询工具，基于真实数据回答，不要编造；
3. 辅导员询问待审核情况时调用 query_pending_audits；
4. 回答简洁、分点，涉及规则时注明来源文档；数据未知时如实说明。"""


def build_agent():
    model = get_chat_model()
    if model is None:
        return None
    return create_react_agent(model, TOOLS, checkpointer=_checkpointer,
                              prompt=SYSTEM_PROMPT)


async def ensure_thread(agent, session_id: str, history: list[dict]):
    """进程重启后 checkpointer 状态丢失：用 DB 历史消息回放恢复记忆"""
    state = await agent.aget_state({"configurable": {"thread_id": session_id}})
    if state.values.get("messages"):
        return
    msgs = []
    for m in history[-20:]:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        else:
            msgs.append(AIMessage(content=m["content"]))
    if msgs:
        await agent.aupdate_state({"configurable": {"thread_id": session_id}},
                                  {"messages": msgs})


async def stream_agent(agent, session_id: str, message: "str | HumanMessage", db, user):
    """流式执行 Agent，逐 token yield 文本增量（message 可为纯文本或多模态 HumanMessage）"""
    config: RunnableConfig = {
        "configurable": {"thread_id": session_id, "db": db, "user": user},
        "recursion_limit": 25,
    }
    inputs = {"messages": [message if isinstance(message, HumanMessage)
                           else HumanMessage(content=message)]}
    async for chunk, meta in agent.astream(inputs, config, stream_mode="messages"):
        if isinstance(chunk, AIMessage) and chunk.content:
            content = chunk.content
            if not isinstance(content, str):  # 视觉模型可能返回 content parts
                content = "".join(p.get("text", "") if isinstance(p, dict) else str(p)
                                  for p in content)
            if content.strip().startswith("{") or getattr(chunk, "tool_calls", None):
                continue  # 过滤工具调用 JSON 噪声
            yield content


async def stream_offline(message: str, history: list[dict]):
    """离线知识库模式：RAG 检索 + 模板组装 + 模拟流式输出"""
    hits = search_knowledge(message, k=3)
    parts = ["（离线知识库模式，未配置大模型 Key，回答基于知识库检索）\n\n"]
    if hits:
        parts.append(f"就「{message}」在知识库中找到以下相关内容：\n\n")
        for i, h in enumerate(hits, 1):
            parts.append(f"{i}. {h['content']}\n\n")
        parts.append("如需更个性化的解答（结合你的学分数据），请在 .env 中配置 LLM_API_KEY 后重启服务。")
    else:
        parts.append("知识库中暂未收录该问题的相关内容，请换个问法，或联系管理员补充知识库"
                     "（server/knowledge_base/ 目录）。")
    text = "".join(parts)
    for i in range(0, len(text), 24):
        yield text[i:i + 24]
        await asyncio.sleep(0.02)
