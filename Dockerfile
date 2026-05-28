# ─────────────────────────────────────────────────────────────
#  스피또 분석기 - Dockerfile
#  Render.com 무료 티어 배포용
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (Playwright Chromium 실행에 필요)
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libx11-6 libxext6 libxrender1 libx11-xcb1 libxcb1 \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium만 설치 (Firefox/WebKit 제외하여 용량 절약)
RUN playwright install chromium

# 앱 소스 복사
COPY . .

# 포트 노출 (Render.com은 $PORT 환경변수 사용)
EXPOSE 10000

# 서버 실행
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
