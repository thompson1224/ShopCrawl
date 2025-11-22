🛠️ 로컬 개발 환경 설정
1단계: 가상환경 생성 및 패키지 설치

bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 가상환경 활성화 (Mac/Linux)
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt


Backend & Core
Python 3.11: 프로젝트의 주 언어.

FastAPI: 고성능 비동기 웹 프레임워크. API 서버 구축.

Uvicorn: ASGI 웹 서버 구현.

SQLAlchemy (ORM): Python 객체와 데이터베이스 간의 매핑 처리.

Pydantic: 데이터 유효성 검사 및 설정 관리.

Crawling & Automation
Playwright (Async): 동적 웹페이지(JavaScript 렌더링 필요) 크롤링 및 브라우저 자동화.

Httpx: 고속 비동기 HTTP 클라이언트 (정적 페이지 크롤링용).

BeautifulSoup4: HTML 파싱 및 데이터 추출.

APScheduler: 백그라운드 크롤링 작업 및 DB 백업 스케줄링 관리.

AI & RAG (Retrieval-Augmented Generation)
LangChain: LLM 애플리케이션 구축을 위한 프레임워크.

Google Gemini API (gemini-2.0-flash): 자연어 처리 및 답변 생성을 위한 무료/고성능 LLM.

ChromaDB: 수집된 핫딜 데이터를 벡터화하여 저장하는 임베딩 데이터베이스 (File-based).

Google Generative AI Embeddings: 텍스트 데이터를 벡터(숫자)로 변환.

Infrastructure & DevOps
Fly.io (PaaS): Docker 컨테이너 기반의 서버 배포 및 호스팅.

Docker: 애플리케이션 컨테이너화 (Playwright 브라우저 환경 포함).

SQLite: 경량화된 파일 기반 관계형 데이터베이스 (Persistent Volume 연동).

Linux (Debian Slim): 컨테이너 베이스 이미지.

Frontend
HTML5 / Vanilla JS: 가벼운 프론트엔드 구현.

Tailwind CSS: 유틸리티 퍼스트 CSS를 통한 반응형 UI 디자인.
