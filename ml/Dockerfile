FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git procps && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-group encoders --no-install-project
COPY . .
RUN uv sync --frozen --no-dev --no-group encoders
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["triagekit", "serve", "--host", "0.0.0.0", "--port", "8000"]
