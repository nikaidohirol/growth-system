"""进程内 TTL 缓存（读多写少的看板/统计场景）

失效策略双保险：
1. TTL 自然过期（默认 30s，环境变量 GROWTH_CACHE_TTL 可调，0 = 完全禁用，测试环境使用）
2. 写路径主动 bump 版本号：任何实体记录/用户变更都会使全部带版本的缓存键失效
   —— 比「精确失效某个键」简单可靠，统计类缓存宁可多算一次也不给脏数据
"""
import os
import time

_ttl = int(os.environ.get("GROWTH_CACHE_TTL", "30"))
_version = 0
_store: dict[str, tuple[int, float, object]] = {}   # key -> (version, expires_at, value)


def bump() -> None:
    """写路径调用：全局版本 +1，并清空旧代数据（等价于全部失效，免去残留键的内存滞留）"""
    global _version
    _version += 1
    _store.clear()


def cached(key: str):
    """装饰器：缓存 async 函数结果（key 需自带作用域区分，如角色/uid/college/查询参数）"""
    def deco(fn):
        async def wrapper(*args, **kwargs):
            v, exp, val = _store.get(key, (None, 0.0, None))
            if v == _version and exp > time.monotonic():
                return val
            val = await fn(*args, **kwargs)
            _store[key] = (_version, time.monotonic() + _ttl, val)
            return val
        return wrapper
    return deco
