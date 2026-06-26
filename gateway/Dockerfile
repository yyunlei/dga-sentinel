FROM python:3.13-slim

WORKDIR /app

# 1) 只复制依赖声明，最大化缓存命中
COPY pyproject.toml ./

# 2) 使用 BuildKit cache 持久化 pip 下载缓存（避免反复下载大 wheel）
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && \
    pip install .

# 3) 再复制代码（改代码不影响依赖层）
COPY shared/ shared/
COPY gateway/ gateway/

EXPOSE 8000
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
