# syntax=docker/dockerfile:1

# ---------- Stage 1: install the dependencies from uv.lock ----------
FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# --no-install-project: the app runs from src/ with flat imports, it is not a package.
# --no-build: fail loudly if a dependency has no prebuilt wheel (no compiler in the image).
RUN uv sync --frozen --no-install-project --no-dev --no-build


# ---------- Stage 2: runtime image ----------
FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
RUN chown -R app:app /app/src/jobagent/data

USER app
EXPOSE 8501

# cli.py is the entry point: `ui` by default, or `run` / `check` as arguments.
ENTRYPOINT ["python", "src/jobagent/cli.py"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8501", "--headless"]
