"""Alembic 环境：URL 从应用配置（app.config / 环境变量）读取，双驱动（SQLite 开发 / PG 生产-CI）

异步驱动（aiosqlite/asyncpg）不能直接用于 Alembic 的同步连接——统一把
scheme 换成同步驱动（sqlite / psycopg 分支），保证 `alembic upgrade head`
在任意 DATABASE_URL 下可用。
"""
import os

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import settings
from app.models.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 优先级：ALEMBIC_URL 环境变量 > DATABASE_URL（异步 scheme 换同步驱动）
_url = os.environ.get("ALEMBIC_URL") or settings.DATABASE_URL
_sync_url = _url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
