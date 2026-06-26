FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
COPY src/common    src/common
COPY src/ai/agents src/ai/agents
CMD ["python", "-m", "ai.agents"]
