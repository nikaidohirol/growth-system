FROM python:3.11-slim

WORKDIR /app

# 默认国内镜像源（本地构建免代理）；海外/CI 可 --build-arg PIP_INDEX_URL= 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
# AUTO_SEED=1 时容器启动自动建表+灌演示数据（已有数据自动跳过）；SEED_RESET=1 强制重建
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
