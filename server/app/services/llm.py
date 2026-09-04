"""LLM 封装 — OpenAI 兼容协议多模型切换（DeepSeek / 通义千问 / OpenAI）

未配置 API Key 时返回 None，上层自动降级为『离线知识库模式』，保证系统无 Key 可跑。
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


@lru_cache
def get_chat_model() -> ChatOpenAI | None:
    if not settings.LLM_API_KEY:
        return None
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        streaming=True,
        temperature=0.3,
        timeout=60,
    )


def llm_available() -> bool:
    return bool(settings.LLM_API_KEY)
