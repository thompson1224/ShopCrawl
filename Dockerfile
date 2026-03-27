FROM python:3.11-slim

WORKDIR /app

# curl_cffi 빌드에 필요한 최소 의존성
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
