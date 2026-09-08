"""RAG 引擎 — FAISS 向量检索 + 双通道 Embedding

- 配置 EMBED_API_KEY：OpenAI 兼容接口（硅基流动 BGE-M3 / 通义 text-embedding）
- 未配置：本地 TF-IDF 哈希向量（零依赖、离线可用，维度 EMBED_DIM，L2 归一化后余弦等价）
知识库来源 knowledge_base/*.md，启动时按标题/段落切块入库。
"""
import hashlib
import math
import re
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.config import settings, BASE_DIR

KB_DIR = BASE_DIR / "knowledge_base"


# ---------------- 本地 Embedding（离线降级） ----------------
class HashTfidfEmbeddings(Embeddings):
    """字符 n-gram TF 向量 + 特征哈希，无需下载任何模型"""
    dim: int = settings.EMBED_DIM

    def _features(self, text: str) -> dict[str, float]:
        text = re.sub(r"\s+", "", text.lower())
        grams = [text[i:i + 2] for i in range(max(len(text) - 1, 0))] or [text]
        tf: dict[str, float] = {}
        for g in grams:
            tf[g] = tf.get(g, 0) + 1
        for k in tf:
            tf[k] /= len(grams)
        return tf

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for g, w in self._features(text).items():
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1 if (h >> 64) % 2 == 0 else -1
            vec[idx] += sign * w
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@lru_cache
def get_embeddings():
    if settings.EMBED_API_KEY:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            api_key=settings.EMBED_API_KEY,
            base_url=settings.EMBED_BASE_URL,
            model=settings.EMBED_MODEL,
            timeout=30,
        )
    return HashTfidfEmbeddings()


def _split_markdown(text: str, source: str) -> list[dict]:
    """按 ## 标题切块，超长段落再按句切分（每块 ~500 字）"""
    chunks: list[dict] = []
    sections = re.split(r"\n(?=##\s)", text)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        title = (sec.splitlines()[0].lstrip("# ").strip() if sec.startswith("#") else source)
        if len(sec) <= 600:
            chunks.append({"text": f"【{title}】\n{sec}", "source": source, "title": title})
            continue
        buf = ""
        for sent in re.split(r"(?<=[。；;！!？?\n])", sec):
            if len(buf) + len(sent) > 600 and buf:
                chunks.append({"text": f"【{title}】\n{buf}", "source": source, "title": title})
                buf = sent
            else:
                buf += sent
        if buf.strip():
            chunks.append({"text": f"【{title}】\n{buf}", "source": source, "title": title})
    return chunks


@lru_cache
def build_vectorstore():
    """构建 FAISS 索引（进程内缓存）"""
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    docs: list[Document] = []
    if KB_DIR.exists():
        for md in sorted(KB_DIR.glob("*.md")):
            for c in _split_markdown(md.read_text(encoding="utf-8"), md.stem):
                docs.append(Document(page_content=c["text"],
                                     metadata={"source": c["source"], "title": c["title"]}))
    if not docs:
        return None
    return FAISS.from_documents(docs, get_embeddings())


def search_knowledge(query: str, k: int = 4) -> list[dict]:
    vs = build_vectorstore()
    if vs is None:
        return []
    hits = vs.similarity_search(query, k=k)
    return [{"content": d.page_content, "source": d.metadata["source"],
             "title": d.metadata["title"]} for d in hits]
