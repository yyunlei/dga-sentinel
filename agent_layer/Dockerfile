FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && \
    pip install .

COPY shared/ shared/
COPY agent_layer/ agent_layer/

CMD ["python", "-m", "agent_layer"]
