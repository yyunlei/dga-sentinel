FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
COPY src/common   src/common
COPY src/business src/business
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip setuptools wheel && pip install .
EXPOSE 8000
CMD ["uvicorn", "business.main:app", "--host", "0.0.0.0", "--port", "8000"]
