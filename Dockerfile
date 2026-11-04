# The notebooks site (notebooks.sustenaut.eu). Build from the repo root:
#   podman build -t notebooks .
# Two stages: Node builds the form widget's bundle from package-lock.json, then the site's image holds Python,
# the locked dependencies, the notebooks and their queries, forms and data, and the bundle. No key, token or
# query result is baked in: BigQuery's key is mounted at run time (k8s/app.yaml), and oauth2-proxy in front
# signs people in (notebooks_lib/serve.py checks their access on each request).
FROM docker.io/library/node:22-slim AS widget
WORKDIR /build
COPY package.json package-lock.json tsconfig.json vite.config.ts ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY widget/ widget/
RUN npm run build

FROM docker.io/library/python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH PORT=8080
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY notebooks_lib/ notebooks_lib/
COPY --from=widget /build/notebooks_lib/static/ notebooks_lib/static/
COPY notebooks/ notebooks/
COPY queries/ queries/
COPY data/ data/
RUN uv sync --locked --no-dev && useradd --create-home --uid 1000 app
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn notebooks_lib.serve:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
