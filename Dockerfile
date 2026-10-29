# Watch Me! single image: api + worker + built SPA (ADR-0027). Target linux/arm64 (Oracle A1).
# Build: docker build --platform linux/arm64 -t watch-me:latest .
# Works with the legacy builder too (no BuildKit-only syntax), so a host without buildx can build it.

# ---- frontend build
FROM node:22.17.0-bookworm-slim AS frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /src/frontend
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---- backend dependencies (locked)
FROM python:3.12.11-slim-bookworm AS backend
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- runtime
FROM python:3.12.11-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 watchme \
    && useradd --system --uid 10001 --gid watchme --home-dir /app --shell /usr/sbin/nologin watchme \
    && mkdir -p /data && chown watchme:watchme /data
WORKDIR /app/backend
COPY --from=backend /app/backend/.venv /app/backend/.venv
COPY backend/ /app/backend/
COPY --from=frontend /src/frontend/dist /app/frontend/dist
COPY deploy/start.sh /usr/local/bin/start.sh
RUN chmod 0755 /usr/local/bin/start.sh
ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SPA_DIR=/app/frontend/dist \
    DATABASE_URL=sqlite:////data/watchme.db \
    STORAGE_ROOT=/data/storage \
    PORT=8000
USER watchme
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)"]
ENTRYPOINT ["tini", "--", "/usr/local/bin/start.sh"]
