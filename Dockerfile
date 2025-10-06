# Python 3.13 기반 이미지
FROM python:3.13-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 및 Playwright 종속성 수동 설치
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    fonts-liberation \
    fonts-unifont \
    libasound2t64 \
    libatk-bridge2.0-0t64 \
    libatk1.0-0t64 \
    libcups2t64 \
    libdbus-1-3 \
    libgbm1 \
    libglib2.0-0t64 \
    libgtk-3-0t64 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxshmfence1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 브라우저 설치 (dependencies 제외)
RUN playwright install chromium

# 앱 코드 복사
COPY . .

# 포트 노출
EXPOSE 8000

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 앱 실행
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
