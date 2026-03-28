# ShopCrawl 작업 내역 정리

> 기간: 2026-03-27 ~ 2026-03-29

---

## 1. 보안 취약점 수정 (2026-03-27)

**커밋:** `c905f8b`

| 항목 | 내용 |
|------|------|
| 중복 라우트 제거 | `naver_callback` 스텁이 실제 구현을 덮어쓰던 문제 수정 |
| 자격증명 로깅 제거 | 서버 시작 시 `SECRET_KEY`, `NAVER_CLIENT_SECRET` 출력하던 코드 삭제 |
| 관리자 엔드포인트 인증 | `/api/admin/sync-rag`에 `ADMIN_SECRET` 검증 추가 |
| CORS 강화 | `allow_origins=["*"]` → `BASE_URL` 기반으로 제한 |

---

## 2. 성능 최적화 — 캐싱 및 환경변수 정리 (2026-03-27)

**커밋:** `1c6f24e`

- `/api/hotdeals` 응답에 30초 TTL 인메모리 캐시 추가
- 크롤링 완료 시 캐시 자동 무효화
- `FLY_APP_NAME` 의존 코드 → `APP_ENV=production` 방식으로 통일
- `models.py` DB 경로도 동일 방식으로 통일 (`42b0ef3`)

---

## 3. Playwright 완전 제거 (2026-03-27 ~ 03-28)

**커밋:** `13b7d4a`, `8fdc7c8`, `e6be898`

| 사이트 | 변경 전 | 변경 후 |
|--------|---------|---------|
| 루리웹 | Playwright | httpx + BeautifulSoup |
| 어미새 | Playwright | httpx + BeautifulSoup |
| Zod | Playwright | curl_cffi (chrome120 TLS 지문 위장) |
| 뽐뿌 | httpx (유지) | - |
| 퀘이사존 | httpx (유지) | - |

**결과:**
- 메모리 사용량 ~800MB → ~150MB
- 5개 스크래퍼 순차 실행 → 전체 병렬(`asyncio.gather`) 실행
- Playwright/Chromium 시스템 의존성 제거 → Docker 이미지 경량화

---

## 4. 배포 환경 전환 — Fly.io → Koyeb (2026-03-28)

**커밋:** `b1d5d6a`, `e4f010a`

- `Procfile` 추가 (Koyeb Git 빌더용)
- `koyeb.yaml` 추가
- `Dockerfile`에서 불필요한 시스템 패키지 제거 (`ca-certificates`만 유지)
- Hetzner + Coolify 이전 계획은 Playwright 제거로 불필요해져 폐기

---

## 5. 스크래퍼 데이터 품질 개선 (2026-03-28 ~ 03-29)

### 5-1. 가격 파싱 정확도 향상

**커밋:** `da4bf3a`, `75a3d8b`

- **퀘이사존**: `span.text-orange` 기반 가격 추출 (`￦ 59,000 (KRW)` 형식 파싱)
- **Zod**: `dl.zod-board--deal-meta dd` 레이블 순회로 가격/배송비 추출
- **공통 헬퍼 `extract_price()` 추가** — 아래 형식 모두 지원:
  - `1,500원`, `5,000원대`
  - `₩143,624`, `₩ 10,150`
  - `1.9만원`, `5만원대`
  - `49,900` (원 표기 없는 콤마 구분 숫자)
- 어미새 `list_adsense` 광고 항목 필터링 추가

**가격 파싱률 변화:**

| 사이트 | 이전 | 이후 |
|--------|------|------|
| Zod | ~60% | 100% |
| 퀘이사존 | ~70% | 100% |
| 루리웹 | ~6% | ~66% |
| 뽐뿌 | ~90% | ~95% |

### 5-2. 루리웹 썸네일 추출

**커밋:** `815641f`

- 목록 페이지에 썸네일 없음 확인 → 개별 포스트 `og:image` 병렬 fetch
- `asyncio.Semaphore(5)`로 동시 요청 수 제한
- 32개 중 ~25개(78%) 썸네일 확보 (나머지 7개는 텍스트 전용 포스트)

---

## 6. 보안 강화 2차 (2026-03-28)

**커밋:** `d421b71`

| 항목 | 내용 |
|------|------|
| XSS 방지 | `innerHTML` 기반 렌더링 → DOM API 기반으로 전면 교체 |
| JWT 저장 방식 | `localStorage` → `HttpOnly` 쿠키로 변경 |
| OAuth state 검증 | 네이버 로그인 콜백에 state 쿠키 검증 추가 |
| 이미지 프록시 SSRF 방지 | 도메인 allowlist 적용, localhost/loopback/redirect 차단 |
| 관리자 엔드포인트 통일 | `/api/crawl-now`, `/api/debug/models` 에도 `ADMIN_SECRET` 검증 + rate limit |
| 입력값 검증 | `page`, `per_page` 범위 검증 추가 |
| RAG 중복 적재 완화 | 링크 해시 기반 문서 ID로 upsert 처리 |

---

## 현재 상태 요약

```
메모리:     ~150MB (Playwright 제거 전 ~800MB)
크롤링:     5개 사이트 완전 병렬 실행
배포:       Koyeb (무료 플랜)
DB:         SQLite (Koyeb 퍼시스턴트 볼륨)
벡터 DB:    ChromaDB + Google Gemini 임베딩
인증:       네이버 OAuth + 로컬 로그인 (HttpOnly 쿠키)
```

## 미완료 / 보류 항목

- [ ] DB 오래된 데이터 자동 정리 (7일 이상 삭제)
- [ ] 루리웹 og:image fetch 재요청 스킵 최적화
- [ ] DB 복합 인덱스 추가 (source + created_at)
