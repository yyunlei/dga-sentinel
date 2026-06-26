FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -U pip setuptools wheel && pip install .
COPY src/common     src/common
COPY src/ai/scoring src/ai/scoring
COPY artifacts/     artifacts/
EXPOSE 8001
CMD ["uvicorn", "ai.scoring.main:app", "--host", "0.0.0.0", "--port", "8001"]
