FROM python:3.13-slim

WORKDIR /app

# 1) 先放依赖声明，最大化缓存命中
COPY pyproject.toml ./
# 如果你有 lock 文件，强烈建议一起 COPY（比如 uv.lock / poetry.lock / pdm.lock）
# COPY uv.lock poetry.lock pdm.lock ./

# 2) pip 缓存持久化 + 先把依赖装好（可复用下载的whl）
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -U pip setuptools wheel && \
    pip install -e .

# 3) 再复制代码/模型文件（改代码不会导致依赖层重装）
COPY shared/ shared/
COPY scoring_service/ scoring_service/
COPY artifacts/ artifacts/

EXPOSE 8001
CMD ["uvicorn", "scoring_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
