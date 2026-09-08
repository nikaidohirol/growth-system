#!/bin/sh
set -e

# SEED_RESET=1 时 seed.py 内部会先 drop 重建库（由 compose 环境变量直接控制）
if [ "$AUTO_SEED" = "1" ]; then
  echo ">>> AUTO_SEED=1：初始化/检查演示数据..."
  python seed.py
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
