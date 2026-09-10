"""pytest 全局环境：必须在导入 app 之前设置

GROWTH_CACHE_TTL=0 禁用看板统计缓存，GROWTH_PROMOTE_INTERVAL=0 禁用惰性晋升节流，
保证「写后立即读」断言的确定性；
压测/生产环境默认 30s TTL / 20s 晋升节流（见 app/cache.py、app/services/audit_flow.py）。
"""
import os

os.environ.setdefault("GROWTH_CACHE_TTL", "0")
os.environ.setdefault("GROWTH_PROMOTE_INTERVAL", "0")
os.environ.setdefault("LLM_API_KEY", "")
