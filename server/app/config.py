"""全局配置 — 统一从环境变量 / .env 读取，端口规范：后端 8000，前端 3000"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # ---- 应用 ----
    APP_NAME: str = "AI 学生成长发展系统 API"
    HOST: str = "0.0.0.0"
    PORT: int = 8000                      # 端口规范：后端固定 8000
    SECRET_KEY: str = "growth-system-secret-key-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'growth_dev.db'}"
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- LLM（OpenAI 兼容协议，支持 deepseek / qwen / openai 切换）----
    LLM_API_KEY: str = ""                 # 为空时进入离线规则模式，系统仍可用
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    # ---- Embedding（RAG 向量化，可用硅基流动 BGE-M3 等）----
    EMBED_API_KEY: str = ""               # 为空时使用本地 TF-IDF 哈希向量（离线可用）
    EMBED_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBED_MODEL: str = "BAAI/bge-m3"
    EMBED_DIM: int = 512                  # 本地哈希向量维度

    # ---- 科大讯飞 TTS（可选，为空时前端降级浏览器合成）----
    IFLYTEK_APP_ID: str = ""
    IFLYTEK_API_KEY: str = ""
    IFLYTEK_API_SECRET: str = ""

    # ---- SMTP 邮件触达（可选，为空时降级为仅站内信）----
    SMTP_HOST: str = ""                   # 如 smtp.qq.com / smtp.163.com
    SMTP_PORT: int = 465                  # 465=SSL，587=STARTTLS
    SMTP_USER: str = ""                   # 发件邮箱账号
    SMTP_PASS: str = ""                   # 邮箱服务商的授权码（非登录密码）
    SMTP_FROM: str = ""                   # 发件人显示地址，默认取 SMTP_USER

    # ---- 权限 ----
    DEAN_UID: str = "D0001"


settings = Settings()
