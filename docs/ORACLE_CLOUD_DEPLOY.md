# Oracle Cloud Free ARM + ShopCrawl 배포 가이드

> Oracle Cloud Always Free Tier (ARM Ampere A1 Core 2개, 50GB 스토리지)

---

## 1. Oracle Cloud 가입

### 1-1. 가입 페이지
```
https://www.oracle.com/cloud/free/
```
**"Start for free"** 클릭

### 1-2. 필요한 것
- 이메일
- 한국 신용/체크카드 (청구되지 않음,verification용)
- 휴대폰 인증

### 1-3. 가입 후 로그인
```
https://cloud.oracle.com/
```

---

## 2. VCN (Virtual Cloud Network) 생성

### 2-1. 리전 선택
- **서울 리전** 또는 **도쿄 리전** 선택 (한국 사용자 빠른 응답)

### 2-2. 네트워킹 → VCN 마법사 시작
```
Create a VCN with Internet Connectivity
```
- VCN Name: `shopcrawl-vcn`
- CIDR Block: `10.0.0.0/16`

### 2-3. 서브넷
자동으로 퍼블릭 서브넷 생성됨

---

## 3. Ubuntu VM 생성 (ARM)

### 3-1. 컴퓨트 → 인스턴스 → 인스턴스 생성

| 설정 | 값 |
|------|-----|
| **Name** | `shopcrawl` |
| **Placement** | Seoul (ap-seoul-1) |
| **Shape** | Ampere (ARM) |
| **Shape Series** | Ampere Altra |
| **Shape Name** | VM.Standard.A1.Flex (0.25 OCPU, 6GB RAM) |

> ⚠️ Free Tier에서는 **VM.Standard.A1.Flex** 2개 또는 **VM.Standard.E2.1.Micro** 1개 무료

### 3-2. 이미지
```
Canonical Ubuntu 22.04
```

### 3-3. 네트워킹
- Virtual Cloud Network: 방금 생성한 VCN 선택
- Subnet: 퍼블릭 서브넷 선택
- Public IP: ✅ 할당 (중요!)

### 3-4. 키 쌍
- 키 생성 또는 기존 키 업로드
- **비밀키 다운로드 (很重要!)**

### 3-5. 방화벽
- SSH (22), HTTP (80), HTTPS (443), Custom (8000) 포트 허용

---

## 4. VM 접속 및 기본 설정

### 4-1. SSH 접속
```bash
# Windows (PowerShell)
ssh -i "path/to/your/private-key.pem" ubuntu@YOUR_VM_PUBLIC_IP

# Mac/Linux
ssh -i "~/Downloads/your-key.pem" ubuntu@YOUR_VM_PUBLIC_IP
```

### 4-2. 기본 패키지 업데이트
```bash
sudo apt update && sudo apt upgrade -y
```

### 4-3. 필요 패키지 설치
```bash
# Docker, Docker Compose, ufw, curl
sudo apt install -y docker.io docker-compose ufw curl
```

### 4-4. Docker 시작 및 자동 실행
```bash
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ubuntu
```

---

## 5. 방화벽 설정 (UFW)

```bash
# SSH 접속 유지
sudo ufw allow 22/tcp

# HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# ShopCrawl (임시/개발용)
sudo ufw allow 8000/tcp

# 내부 통신 허용
sudo ufw allow from 10.0.0.0/16 to any port 2375

# 방화벽 활성화
sudo ufw enable
sudo ufw status
```

---

## 6. Oracle Cloud 방화벽 (네트워크 보안)

### 6-1. VCN 방화벽 규칙 추가
```
네트워킹 → Virtual Cloud Network → 보안 목록 → 수신 규칙 추가

- Source CIDR: 0.0.0.0/0
- IP Protocol: TCP
- Destination Port Range: 8000, 443, 80
```

---

## 7. ShopCrawl 배포

### 7-1. 프로젝트 클론
```bash
cd ~
git clone https://github.com/thompson1224/ShopCrawl.git
cd ShopCrawl
```

### 7-2. .env 파일 생성
```bash
cat > .env << 'EOF'
APP_ENV=production
PORT=8000
GOOGLE_API_KEY=your_google_api_key_here
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
ADMIN_SECRET=your_strong_admin_secret_here
BASE_URL=https://shop.yourdomain.com
EOF
```

### 7-3. Docker Compose 파일 생성
```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  shopcrawl:
    build: .
    container_name: shopcrawl
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./chroma_db:/app/chroma_db
    env_file:
      - .env
    environment:
      - APP_ENV=production
      - PORT=8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 3G
        reservations:
          memory: 1G
EOF
```

### 7-4. 데이터 디렉토리 생성
```bash
mkdir -p data chroma_db backups
```

### 7-5. Docker 빌드 및 실행
```bash
sudo docker-compose up -d --build
```

### 7-6. 로그 확인
```bash
sudo docker-compose logs -f
```

### 7-7. 헬스체크
```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
curl http://localhost:8000/health/vectorstore
```

---

## 8. Nginx 리버스 프록시 + SSL

### 8-1. Certbot 설치
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 8-2. Nginx 설치
```bash
sudo apt install -y nginx
```

### 8-3. Nginx 설정
```bash
sudo nano /etc/nginx/sites-available/shopcrawl
```

```nginx
server {
    listen 80;
    server_name shop.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/shopcrawl /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 8-4. SSL 인증서 발급
```bash
sudo certbot --nginx -d shop.yourdomain.com
```

### 8-5. 자동 갱신 확인
```bash
sudo certbot renew --dry-run
```

---

## 9. Cloudflare DNS 설정

### 9-1. Cloudflare Dashboard
```
https://dash.cloudflare.com
```

### 9-2. DNS 설정
| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | shop | YOUR_VM_PUBLIC_IP | 🔵 Proxied |
| A | api | YOUR_VM_PUBLIC_IP | 🔵 Proxied |

### 9-3. SSL 설정
- SSL/TLS → Mode: **Full** 또는 **Strict**

---

## 10. 백업 설정 (Cron)

```bash
crontab -e
```

```
# 매일 새벽 3시 백업 (선택)
0 3 * * * /home/ubuntu/ShopCrawl/backup.sh >> /home/ubuntu/backups/cron.log 2>&1
```

---

## 11. 업데이트 배포

```bash
cd ~/ShopCrawl
git pull origin main
sudo docker-compose down
sudo docker-compose up -d --build
```

---

## 빠른 체크리스트

```
✅ Oracle Cloud 인스턴스 실행 중
✅ 공인 IP 확인
✅ SSH 접속 가능
✅ Docker 설치됨
✅ 방화벽 열림 (80, 443, 8000)
✅ ShopCrawl 실행 중 (http://VM_IP:8000)
✅ DNS 설정 완료
✅ SSL 인증서 발급 완료
✅ Cloudflare 연결 확인
```

---

## 문제 해결

### Docker 로그 확인
```bash
sudo docker-compose logs shopcrawl
sudo docker logs shopcrawl -f
```

### 포트 확인
```bash
sudo ss -tlnp | grep -E ':(80|443|8000)'
```

### 방화벽 확인
```bash
sudo ufw status
sudo iptables -L -n
```

### Oracle Cloud 상태
```
컴퓨트 → 인스턴스 → shopcrawl → 리소스 →VNIC → 보안 목록
```

---

## 참고 링크

- Oracle Cloud Free Tier: https://www.oracle.com/cloud/free/
- Cloudflare: https://dash.cloudflare.com
- Certbot: https://certbot.eff.org/
