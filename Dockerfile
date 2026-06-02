FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_SYSTEM_PYTHON=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --locked --no-dev -o requirements.txt \
    && uv pip install --system -r requirements.txt

# Copy application layers
COPY frontend/ ./frontend/
COPY backend/ ./backend/
COPY pipeline/ ./pipeline/

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "backend.src.app:app", "--host", "0.0.0.0", "--port", "8000"]
