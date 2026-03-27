FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 도구 설치
# curl_cffi 및 기본 동작을 위해 필요한 최소한의 라이브러리 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 및 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# Railway가 제공하는 PORT 사용
EXPOSE 8080  

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
