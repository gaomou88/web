FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=UTC \
    DATA_DIR=/data FRONTEND_DIR=/app/frontend
WORKDIR /app

# 国内服务器下载慢时可在 docker-compose.yml 里设置 PIP_INDEX_URL 为国内镜像
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY backend/requirements.txt .
RUN pip install -i "$PIP_INDEX_URL" -r requirements.txt

COPY backend/app ./app
COPY frontend ./frontend
COPY docs ./docs
RUN useradd -r -u 10001 zyll && mkdir -p /data && chown -R zyll /data
USER zyll
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "5"]
