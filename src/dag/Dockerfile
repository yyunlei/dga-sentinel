FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
COPY src/common     src/common
COPY src/ai/scoring src/ai/scoring
COPY src/dag        src/dag
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
CMD ["python", "-m", "dag.runtime"]
