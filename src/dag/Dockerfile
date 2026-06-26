FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
COPY src/common     src/common
COPY src/dag        src/dag
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install ".[dag]"
CMD ["python", "-m", "dag.runtime"]
