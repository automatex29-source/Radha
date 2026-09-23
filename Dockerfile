# RADHA — one image with the web app and the API.
#   docker compose up --build      (see README.md)

# ---- 1. Build the web app ------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/.npmrc ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. API server (also serves the built web app) -------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    FASTEMBED_CACHE_PATH=/app/cache/fastembed

# nodejs: lets the app builder run JavaScript tests in its sandbox.
# util-linux: provides `unshare` for the code sandbox. Fonts: Unicode/Japanese text in PDFs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs util-linux fonts-dejavu-core fonts-ipafont-gothic \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

COPY backend/ ./
COPY --from=frontend /frontend/build /app/frontend/build
RUN mkdir -p /app/cache/fastembed

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
