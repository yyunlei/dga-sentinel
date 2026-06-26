FROM python:3.13-slim

WORKDIR /app

# 先只复制依赖声明文件，最大化缓存命中
COPY pyproject.toml ./
# 如果你有 lock 文件（强烈建议），也一起复制：
# COPY uv.lock poetry.lock pdm.lock requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && \
    pip install .

# 再复制业务代码（改代码不会让依赖层失效）
COPY shared/ shared/
COPY scoring_service/ scoring_service/
COPY dag_engine/ dag_engine/

CMD ["python", "-m", "dag_engine.runtime"]

