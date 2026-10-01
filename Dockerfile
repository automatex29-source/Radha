# RADHA — one image with the web app and the API.
#   docker compose up --build      (see README.md)

# ---- 1. Build the web app ------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/.npmrc ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build \
    && find build -type f \( -name '*.js' -o -name '*.css' -o -name '*.svg' -o -name '*.html' \) -exec gzip -k -9 {} +

# ---- 2. API server (also serves the built web app) -------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    FASTEMBED_CACHE_PATH=/app/cache/fastembed

# nodejs: lets the app builder run JavaScript tests in its sandbox.
# util-linux: provides `unshare` for the code sandbox. Fonts: Unicode/Japanese text in PDFs.
# tesseract-ocr: reads text in photos and scanned PDFs people upload.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs util-linux fonts-dejavu-core fonts-ipafont-gothic tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

COPY backend/ ./
COPY --from=frontend /frontend/build /app/frontend/build
# Download the document-search model now, not on the first file someone uploads after each restart.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')" \
    || mkdir -p /app/cache/fastembed

EXPOSE 8001
# Hosting platforms (Railway, Render, Fly…) pass the port to listen on in $PORT.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --proxy-headers --forwarded-allow-ips='*'"]
