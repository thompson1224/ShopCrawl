# Python 3.13 기반 이미지 사용
FROM python:3.13-slim

# 작업 디렉토리 설정 (컨테이너 안에서 /app 폴더를 기본 위치로)
WORKDIR /app

# Playwright와 Chromium이 필요로 하는 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 파일을 컨테이너로 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 브라우저 설치
RUN playwright install chromium && \
    playwright install-deps chromium

# 프로젝트의 모든 파일을 컨테이너로 복사
COPY . .

# 포트 8000번 노출 (FastAPI가 사용하는 포트)
EXPOSE 8000

# 환경 변수 설정 (Python 출력 버퍼링 비활성화)
ENV PYTHONUNBUFFERED=1

# 컨테이너가 시작되면 uvicorn으로 FastAPI 앱 실행
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
