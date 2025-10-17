from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy import desc
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from auth import create_access_token, get_current_user, get_current_user_required, get_db
from models import User
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import uvicorn
import asyncio
import os
import re
import httpx
from playwright.async_api import async_playwright
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from models import HotDeal, SessionLocal
from datetime import datetime, timedelta
import logging
import pytz

# 환경변수 로드 (선택)
from dotenv import load_dotenv
load_dotenv()

# 디버깅: 환경변수 확인
print("=" * 50)
print("🔍 환경변수 로드 확인:")
print(f"SECRET_KEY: {os.getenv('SECRET_KEY', 'NOT_FOUND')[:20]}...")
print(f"NAVER_CLIENT_ID: {os.getenv('NAVER_CLIENT_ID', 'NOT_FOUND')}")
print(f"NAVER_CLIENT_SECRET: {os.getenv('NAVER_CLIENT_SECRET', 'NOT_FOUND')[:10]}...")
print("=" * 50)


# Railway에서 제공하는 PORT 사용 (없으면 8000)
PORT = int(os.getenv("PORT", 8000))

# 네이버 로그인 콜백 URL (배포 후 변경 필요)
RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_CALLBACK_URL = f"https://{RAILWAY_URL}/api/auth/naver/callback" if RAILWAY_URL != "localhost:8000" else "http://localhost:8000/api/auth/naver/callback"
# # 네이버 설정
# NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
# NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
# NAVER_CALLBACK_URL = "http://localhost:8000/api/auth/naver/callback"

# if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
#     print("⚠️ 경고: 네이버 로그인 키가 설정되지 않았습니다!")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 정적 파일 마운트 (templates 폴더)
try:
    app.mount("/static", StaticFiles(directory="templates"), name="static")
except:
    pass

templates = Jinja2Templates(directory="templates")

# CORS 설정
@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self';")
    return response

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 데이터베이스 세션
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 크롤링 함수들
async def scrape_ppomppu():
    logger.info("뽐뿌 크롤링 시작")
    url = 'https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu'
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10.0)
            response.raise_for_status()
    except httpx.RequestError: 
        logger.error("뽐뿌 크롤링 실패")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    deal_list = []
    base_url = "https://www.ppomppu.co.kr/zboard/"
    main_table = soup.find('table', id='revolution_main_table')
    if not main_table: 
        return []
    
    for item in main_table.find_all('tr', class_='baseList'):
        try:
            title_cell = item.find('td', class_='title')
            author_cell = item.find('span', 'baseList-name')
            if not (title_cell and author_cell): continue
            title_tag = title_cell.find('a', class_='baseList-title')
            if title_tag and 'id=ppomppu' in title_tag['href']:
                full_title = title_tag.get_text(strip=True)
                link = base_url + title_tag['href'] if title_tag['href'].startswith("view.php") else title_tag['href']
                thumbnail_tag = title_cell.find('img')
                thumbnail_src = thumbnail_tag['src'] if thumbnail_tag else ""
                if thumbnail_src.startswith('//'): 
                    thumbnail = 'https:' + thumbnail_src
                else: 
                    thumbnail = thumbnail_src
                source = re.search(r'\[(.*?)\]', full_title).group(1) if re.search(r'\[(.*?)\]', full_title) else "기타"
                price_match = re.search(r'(\d{1,3}(?:,\d{3})*원)', full_title)
                price = price_match.group(1) if price_match else "가격 정보 없음"
                shipping = "무료배송" if "무료" in full_title or "무배" in full_title else "배송비 정보 없음"
                clean_title = re.sub(r'\[.*?\]|(\d{1,3}(?:,\d{3})*원)|\s*\(?\d+\)?$|\s*/\s*무료배송|\s*/\s*무배', '', full_title).strip()
                deal_list.append({'thumbnail': thumbnail, 'source': '뽐뿌', 'author': author_cell.text.strip(), 'title': clean_title, 'price': price, 'shipping': shipping, 'link': link})
        except Exception: 
            continue
    
    logger.info(f"뽐뿌 크롤링 완료: {len(deal_list)}개")
    return deal_list

async def scrape_ruliweb():
    logger.info("루리웹 크롤링 시작")
    deal_list = []
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--disable-dev-shm-usage', '--no-sandbox'])
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font"] else route.continue_())
            await page.goto('https://bbs.ruliweb.com/market/board/1020', wait_until='domcontentloaded', timeout=15000)
            
            list_selector = 'table.board_list_table tbody tr.table_body'
            await page.wait_for_selector(list_selector, timeout=10000)
            posts = await page.query_selector_all(list_selector)

            for item in posts:
                try:
                    is_notice = await item.evaluate('(element) => element.classList.contains("notice")')
                    if is_notice: continue

                    title_tag = await item.query_selector('a.deco')
                    if not title_tag: continue
                    
                    full_title = (await title_tag.inner_text()).strip()
                    link = await title_tag.get_attribute('href')
                    if link and link.startswith('/'): 
                        link = 'https://bbs.ruliweb.com' + link
                    
                    author_tag = await item.query_selector('td.writer a')
                    author = (await author_tag.inner_text()).strip() if author_tag else "작성자"

                    thumbnail = ""
                    price_match = re.search(r'(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)', full_title)
                    price = price_match.group(1) if price_match else "가격 정보 없음"
                    clean_title = re.sub(r'\[.*?\]|\s*\(\d+\)$|\s*\(?(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)\)?', '', full_title).strip()
                    
                    deal_list.append({'thumbnail': thumbnail, 'source': '루리웹', 'author': author, 'title': clean_title, 'price': price, 'shipping': '정보 없음', 'link': link})
                except Exception: 
                    continue
            
            await browser.close()
    except Exception as e:
        logger.error(f"루리웹 크롤링 오류: {e}")
        if browser: 
            await browser.close()
    
    logger.info(f"루리웹 크롤링 완료: {len(deal_list)}개")
    return deal_list

async def scrape_zod():
    logger.info("Zod 크롤링 시작")
    deal_list = []
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'])
            context = await browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font"] else route.continue_())
            
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            await page.goto('https://zod.kr/deal', wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)
            
            try:
                await page.wait_for_selector('ul.app-board-template-list', state='attached', timeout=8000)
            except: 
                pass
            
            posts = await page.query_selector_all('ul.app-board-template-list li')
            if not posts:
                posts = await page.query_selector_all('li[class*="app-list"]')
            
            for item in posts:
                try:
                    text_content = await item.inner_text()
                    if not text_content or '공지' in text_content[:10]: 
                        continue
                    
                    link_tag = await item.query_selector('a[href*="/deal/"]')
                    if not link_tag: 
                        continue
                    
                    href = await link_tag.get_attribute('href')
                    if not href or '/deal/' not in href: 
                        continue
                    link = 'https://zod.kr' + href if href.startswith('/') else href
                    
                    thumbnail = ""
                    img = await item.query_selector('img')
                    if img:
                        thumbnail_src = await img.get_attribute('src')
                        if thumbnail_src:
                            if thumbnail_src.startswith('//'):
                                thumbnail = 'https:' + thumbnail_src
                            elif thumbnail_src.startswith('http'):
                                thumbnail = thumbnail_src
                    
                    title = "제목 없음"
                    title_span = await item.query_selector('span.app-list-title-item')
                    if title_span:
                        title = await title_span.inner_text()
                        title = title.strip()
                    
                    price = "가격 정보 없음"
                    strong_tags = await item.query_selector_all('strong')
                    for strong in strong_tags:
                        strong_text = await strong.inner_text()
                        if '원' in strong_text or ',' in strong_text:
                            price = strong_text.strip()
                            break
                    
                    author = "작성자"
                    member_div = await item.query_selector('div.app-list-member')
                    if member_div:
                        member_text = await member_div.inner_text()
                        if member_text:
                            author = member_text.strip().split('\n')[0]
                    
                    deal_list.append({'thumbnail': thumbnail, 'source': 'Zod', 'author': author, 'title': title, 'price': price, 'shipping': '정보 없음', 'link': link})
                except Exception: 
                    continue
            
            await browser.close()
    except Exception as e:
        logger.error(f"Zod 크롤링 오류: {e}")
        if browser: 
            await browser.close()
    
    logger.info(f"Zod 크롤링 완료: {len(deal_list)}개")
    return deal_list

#어미새 크롤
async def scrape_eomisae():
    logger.info("어미새 크롤링 시작")
    deal_list = []
    browser = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # JavaScript 감지 우회
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            
            logger.info("어미새 페이지 로딩 중...")
            await page.goto('https://eomisae.co.kr/fs', wait_until='networkidle', timeout=20000)
            await page.wait_for_timeout(3000)
            
            # 페이지 HTML 확인
            content = await page.content()
            logger.info(f"어미새 페이지 로딩 완료, HTML 길이: {len(content)}")
            
            # 게시글 리스트 대기
            try:
                await page.wait_for_selector('article, .card_el, .list-item', timeout=5000)
            except:
                logger.warning("어미새: 게시글 셀렉터 대기 실패")
            
            # 여러 셀렉터 시도
            posts = []
            selectors = [
                'article',
                '.card_el',
                'div[class*="card"]',
                'li[class*="item"]',
                '.list-item',
                '[data-post]'
            ]
            
            for selector in selectors:
                posts = await page.query_selector_all(selector)
                if posts:
                    logger.info(f"어미새: '{selector}' 셀렉터로 {len(posts)}개 발견")
                    break
            
            if not posts:
                logger.warning("어미새: 게시글을 찾을 수 없음")
                # HTML 일부 출력 (디버깅용)
                logger.debug(f"어미새 HTML 샘플: {content[:500]}")
                await browser.close()
                return []
            
            for idx, item in enumerate(posts[:20]):  # 최대 20개만
                try:
                    # 모든 텍스트 추출
                    text_content = await item.inner_text()
                    
                    # 링크 찾기
                    link_tag = await item.query_selector('a')
                    if not link_tag:
                        continue
                    
                    link_href = await link_tag.get_attribute('href')
                    if not link_href:
                        continue
                    
                    if link_href.startswith('/'):
                        link = 'https://eomisae.co.kr' + link_href
                    elif link_href.startswith('http'):
                        link = link_href
                    else:
                        link = 'https://eomisae.co.kr/' + link_href
                    
                    # 제목 추출 (여러 방법 시도)
                    title = ""
                    title_selectors = ['h3', 'h2', '.title', '[class*="title"]', 'a']
                    for sel in title_selectors:
                        title_tag = await item.query_selector(sel)
                        if title_tag:
                            title_text = await title_tag.inner_text()
                            if title_text and len(title_text.strip()) > 3:
                                title = title_text.strip()
                                break
                    
                    if not title:
                        # 텍스트에서 첫 줄 사용
                        lines = text_content.strip().split('\n')
                        title = lines[0][:100] if lines else f"어미새 핫딜 #{idx+1}"
                    
                    # 작성자
                    author = "작성자"
                    author_selectors = ['.user', '.author', 'span[class*="user"]', 'span[class*="author"]']
                    for sel in author_selectors:
                        author_tag = await item.query_selector(sel)
                        if author_tag:
                            author_text = await author_tag.inner_text()
                            if author_text:
                                author = author_text.strip()
                                break
                    
                    # 썸네일
                    thumbnail = ""
                    img_tag = await item.query_selector('img')
                    if img_tag:
                        thumbnail_src = await img_tag.get_attribute('src')
                        if thumbnail_src:
                            if thumbnail_src.startswith('//'):
                                thumbnail = 'https:' + thumbnail_src
                            elif thumbnail_src.startswith('http'):
                                thumbnail = thumbnail_src
                            elif thumbnail_src.startswith('/'):
                                thumbnail = 'https://eomisae.co.kr' + thumbnail_src
                    
                    # 가격 추출
                    price_match = re.search(r'(\d{1,3}(?:,\d{3})*원)', title)
                    price = price_match.group(1) if price_match else "가격 정보 없음"
                    
                    # 배송비
                    shipping = "무료배송" if "무료" in title or "무배" in title else "정보 없음"
                    
                    deal_list.append({
                        'thumbnail': thumbnail,
                        'source': '어미새',
                        'author': author,
                        'title': title,
                        'price': price,
                        'shipping': shipping,
                        'link': link
                    })
                    
                    logger.debug(f"어미새 항목 {idx+1}: {title[:30]}...")
                    
                except Exception as e:
                    logger.warning(f"어미새 항목 {idx+1} 파싱 오류: {e}")
                    continue
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"어미새 크롤링 전체 오류: {e}")
        if browser:
            await browser.close()
    
    logger.info(f"어미새 크롤링 완료: {len(deal_list)}개")
    return deal_list





# models.py에도 추가
KST = pytz.timezone('Asia/Seoul')

async def crawl_and_save_to_db():
    logger.info(f"=== 백그라운드 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 모든 크롤러 실행
    tasks = [scrape_ppomppu(), scrape_ruliweb(), scrape_zod(), scrape_eomisae()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_deals = []
    for result in results:
        if not isinstance(result, Exception):
            all_deals.extend(result)
    
    # DB에 저장 (중복 체크 개선)
    db = SessionLocal()
    new_count = 0
    duplicate_count = 0
    error_count = 0
    
    try:
        for deal in all_deals:
            try:
                existing = db.query(HotDeal).filter(HotDeal.link == deal['link']).first()
                
                if existing:
                    # 기존 데이터 업데이트
                    existing.title = deal['title']
                    existing.price = deal['price']
                    existing.shipping = deal['shipping']
                    existing.thumbnail = deal['thumbnail']
                    duplicate_count += 1
                else:
                    # 새 데이터 추가
                    db_deal = HotDeal(**deal, created_at=datetime.now(KST).replace(tzinfo=None))
                    db.add(db_deal)
                    new_count += 1
                
                db.flush()
                
            except Exception as item_error:
                logger.warning(f"항목 저장 실패: {deal.get('link', 'unknown')} - {str(item_error)}")
                error_count += 1
                continue
        
        db.commit()
        
        # DB 전체 개수 확인
        total_count = db.query(HotDeal).count()
        logger.info(f"✅ DB 저장 완료: 신규 {new_count}개, 업데이트 {duplicate_count}개, 오류 {error_count}개, 전체 {total_count}개 - {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        logger.error(f"❌ DB 저장 전체 오류: {e}")
        db.rollback()
    finally:
        db.close()

# 스케줄러 설정
scheduler = AsyncIOScheduler()

# FastAPI 이벤트 핸들러
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 서버 시작: 백그라운드 스케줄러 활성화")
    
    # 첫 크롤링 실행
    await crawl_and_save_to_db()
    
    # 1분마다 크롤링 스케줄 (테스트용, 실제로는 5분 추천)
    scheduler.add_job(crawl_and_save_to_db, 'interval', minutes=1, id='crawl_job')
    scheduler.start()
    logger.info("⏰ 1분마다 자동 크롤링 스케줄 등록")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 서버 종료: 스케줄러 정지")
    scheduler.shutdown()

# API 엔드포인트 (페이지네이션 추가)
@app.get('/api/hotdeals')
async def hotdeals(
    source: str = "all", 
    page: int = 1, 
    per_page: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(HotDeal)
    
    if source != "all":
        query = query.filter(HotDeal.source == source)
    
    # 전체 개수
    total = query.count()
    
    # id 기준 내림차순 (가장 확실한 방법)
    query = query.order_by(desc(HotDeal.id))
    
    # 페이지네이션
    offset = (page - 1) * per_page
    deals = query.offset(offset).limit(per_page).all()
    
    # 총 페이지 수
    total_pages = (total + per_page - 1) // per_page
    
    logger.info(f"API 요청: {source}, 페이지 {page}/{total_pages} - {len(deals)}개 반환")
    
    return {
        "deals": [deal.to_dict() for deal in deals],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages
        }
    }

# 전체 통계 API (선택)
@app.get('/api/stats')
async def stats(db: Session = Depends(get_db)):
    total = db.query(HotDeal).count()
    ppomppu_count = db.query(HotDeal).filter(HotDeal.source == '뽐뿌').count()
    ruliweb_count = db.query(HotDeal).filter(HotDeal.source == '루리웹').count()
    zod_count = db.query(HotDeal).filter(HotDeal.source == 'Zod').count()
    eomisae_count = db.query(HotDeal).filter(HotDeal.source == '어미새').count()
    
    return {
        "total": total,
        "ppomppu": ppomppu_count,
        "ruliweb": ruliweb_count,
        "zod": zod_count,
        "eomisae" : eomisae_count
    }

# 수동 크롤링 API (테스트용)
@app.post('/api/crawl-now')
async def manual_crawl():
    logger.info("수동 크롤링 요청")
    await crawl_and_save_to_db()
    return {"status": "크롤링 완료"}

# 이미지 프록시
@app.get("/image-proxy")
async def image_proxy(url: str, source: str = "뽐뿌"):
    referer_map = { "뽐뿌": "https://www.ppomppu.co.kr/", "루리웹": "https://bbs.ruliweb.com/", "Zod": "https://zod.kr/", "어미새": "https://eomisae.co.kr/"}
    headers = { 'Referer': referer_map.get(source, "https://www.google.com/"), 'User-Agent': 'Mozilla/5.0' }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            media_type = response.headers.get('content-type', 'image/jpeg')
            return Response(content=response.content, media_type=media_type)
        except Exception as e:
            logger.error(f"이미지 프록시 오류: {e}")
            return Response(status_code=404)
        
# 네이버 로그인 시작
@app.get('/api/auth/naver/login')
async def naver_login():
    """네이버 로그인 페이지로 리다이렉트"""
    import secrets
    state = secrets.token_urlsafe(16)
    
    naver_auth_url = (
        f"https://nid.naver.com/oauth2.0/authorize"
        f"?response_type=code"
        f"&client_id={NAVER_CLIENT_ID}"
        f"&redirect_uri={NAVER_CALLBACK_URL}"
        f"&state={state}"
    )
    
    return {"url": naver_auth_url}

# 네이버 로그인 콜백
@app.get('/api/auth/naver/callback')
async def naver_callback(code: str, state: str, db: Session = Depends(get_db)):
    """네이버 로그인 콜백 처리"""
    
    # 1. 액세스 토큰 발급
    token_url = "https://nid.naver.com/oauth2.0/token"
    token_params = {
        "grant_type": "authorization_code",
        "client_id": NAVER_CLIENT_ID,
        "client_secret": NAVER_CLIENT_SECRET,
        "code": code,
        "state": state
    }
    
    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, params=token_params, timeout=10.0)
        token_data = token_response.json()
        
        if "access_token" not in token_data:
            raise HTTPException(status_code=400, detail="네이버 로그인 실패")
        
        access_token = token_data["access_token"]
        
        # 2. 사용자 정보 가져오기
        user_info_url = "https://openapi.naver.com/v1/nid/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        user_response = await client.get(user_info_url, headers=headers, timeout=10.0)
        user_data = user_response.json()
        
        if user_data.get("resultcode") != "00":
            raise HTTPException(status_code=400, detail="사용자 정보 가져오기 실패")
        
        naver_user = user_data["response"]
        provider_id = naver_user["id"]
        email = naver_user.get("email", "")
        name = naver_user.get("name", "")
        profile_image = naver_user.get("profile_image", "")
        
        # 3. DB에서 사용자 찾기 또는 생성
        user = db.query(User).filter(
            User.provider == "naver",
            User.provider_id == provider_id
        ).first()
        
        if not user:
            # 신규 사용자 생성
            user = User(
                username=f"naver_{provider_id[:10]}",
                email=email,
                provider="naver",
                provider_id=provider_id,
                profile_image=profile_image,
                hashed_password=""
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # 4. JWT 토큰 생성
        jwt_token = create_access_token(data={"sub": user.id})
        
        # 5. 프론트엔드로 리다이렉트 (토큰 전달)
        frontend_url = f"http://localhost:8000/?token={jwt_token}"
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=frontend_url)

# 현재 유저 정보 조회
@app.get('/api/auth/me')
async def get_me(current_user: User = Depends(get_current_user_required)):
    """현재 로그인한 유저 정보"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "provider": current_user.provider,
        "profile_image": current_user.profile_image,
        "created_at": current_user.created_at.strftime('%Y-%m-%d')
    }

@app.get('/api/auth/naver/callback')
async def naver_callback(code: str, state: str, db: Session = Depends(get_db)):
    """네이버 로그인 콜백 처리"""
    
    print(f"🔵 네이버 콜백 시작: code={code[:10]}...")
    
    # ... (토큰 발급 코드)
    
    print(f"✅ 네이버 액세스 토큰: {access_token[:20]}...")
    
    # ... (사용자 정보 가져오기)
    
    print(f"✅ 네이버 사용자 정보: {naver_user}")
    
    # ... (DB 저장)
    
    print(f"✅ 유저 생성/조회 완료: {user.username}")
    
    # JWT 토큰 생성
    jwt_token = create_access_token(data={"sub": user.id})
    print(f"✅ JWT 토큰 생성: {jwt_token[:30]}...")
    
    # 프론트엔드로 리다이렉트
    frontend_url = f"http://localhost:8000/?token={jwt_token}"
    
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=frontend_url)



# 정적 파일 제공
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

@app.get("/", response_class=FileResponse)
async def read_root():
    return os.path.join(templates_dir, "index.html")

app.mount("/", StaticFiles(directory=templates_dir, html=True), name="static")

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
