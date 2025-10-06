from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
from bs4 import BeautifulSoup
import uvicorn
import asyncio
import os
import re
import httpx
from playwright.async_api import async_playwright

app = FastAPI()

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self';")
    return response

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- 크롤링 함수들 ---

async def scrape_zod():
    deal_list = []
    browser = None
    try:
        print("Zod 크롤러 시작...")
        async with async_playwright() as p:
            # headless 브라우저 감지 우회
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage'
                ]
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            # JavaScript로 webdriver 감지 우회
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            print("Zod.kr 접속 중...")
            await page.goto('https://zod.kr/deal', wait_until='load', timeout=20000)
            
            # 충분한 대기 시간
            print("페이지 렌더링 대기 중...")
            await page.wait_for_timeout(5000)
            
            # selector 대기 (state를 attached로 변경)
            try:
                await page.wait_for_selector('ul.app-board-template-list', state='attached', timeout=10000)
            except:
                print("게시판 리스트를 찾을 수 없음, 대체 selector 시도")
                await page.wait_for_timeout(2000)
            
            posts = await page.query_selector_all('ul.app-board-template-list li')
            
            if not posts:
                # 대체 selector 시도
                posts = await page.query_selector_all('li[class*="app-list"]')
            
            print(f"Zod 게시글 {len(posts)}개 발견")
            
            for item in posts:
                try:
                    # 전체 텍스트 확인 (공지사항 필터링)
                    text_content = await item.inner_text()
                    if not text_content or '공지' in text_content[:10]:
                        continue
                    
                    # 링크
                    link_tag = await item.query_selector('a[href*="/deal/"]')
                    if not link_tag:
                        link_tag = await item.query_selector('a')
                    if not link_tag:
                        continue
                    
                    href = await link_tag.get_attribute('href')
                    if not href or '/deal/' not in href:
                        continue
                    
                    link = 'https://zod.kr' + href if href.startswith('/') else href
                    
                    # 썸네일
                    thumbnail = ""
                    img = await item.query_selector('img')
                    if img:
                        thumbnail_src = await img.get_attribute('src')
                        if thumbnail_src:
                            if thumbnail_src.startswith('//'):
                                thumbnail = 'https:' + thumbnail_src
                            elif thumbnail_src.startswith('http'):
                                thumbnail = thumbnail_src
                    
                    # 제목
                    title = "제목 없음"
                    title_span = await item.query_selector('span.app-list-title-item')
                    if title_span:
                        title = await title_span.inner_text()
                        title = title.strip()
                    else:
                        lines = text_content.split('\n')
                        for line in lines:
                            if line.strip() and len(line.strip()) > 5:
                                title = line.strip()
                                break
                    
                    # 가격
                    price = "가격 정보 없음"
                    strong_tags = await item.query_selector_all('strong')
                    for strong in strong_tags:
                        strong_text = await strong.inner_text()
                        strong_text = strong_text.strip()
                        if '원' in strong_text or ',' in strong_text:
                            price = strong_text
                            break
                    
                    # 작성자
                    author = "작성자"
                    member_div = await item.query_selector('div.app-list-member')
                    if member_div:
                        member_text = await member_div.inner_text()
                        if member_text:
                            author = member_text.strip().split('\n')[0]
                    
                    deal_list.append({
                        'thumbnail': thumbnail,
                        'source': 'Zod',
                        'author': author,
                        'title': title,
                        'price': price,
                        'shipping': '정보 없음',
                        'link': link
                    })
                    
                except Exception as e:
                    print(f"Zod 항목 파싱 오류: {e}")
                    continue
            
            print(f"Zod 크롤링 완료: {len(deal_list)}개 항목")
            await browser.close()
            browser = None
            
    except Exception as e:
        print(f"Zod Playwright 크롤링 중 오류 발생: {e}")
        if browser:
            await browser.close()
        return []
    
    return deal_list




async def scrape_ppomppu():
    # (안정적인 뽐뿌 크롤러)
    url = 'https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu'
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10.0)
            response.raise_for_status()
    except httpx.RequestError: return []
    soup = BeautifulSoup(response.text, 'html.parser')
    deal_list = []
    base_url = "https://www.ppomppu.co.kr/zboard/"
    main_table = soup.find('table', id='revolution_main_table')
    if not main_table: return []
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
                if thumbnail_src.startswith('//'): thumbnail = 'https:' + thumbnail_src
                else: thumbnail = thumbnail_src
                source = re.search(r'\[(.*?)\]', full_title).group(1) if re.search(r'\[(.*?)\]', full_title) else "기타"
                price_match = re.search(r'(\d{1,3}(?:,\d{3})*원)', full_title)
                price = price_match.group(1) if price_match else "가격 정보 없음"
                shipping = "무료배송" if "무료" in full_title or "무배" in full_title else "배송비 정보 없음"
                clean_title = re.sub(r'\[.*?\]|(\d{1,3}(?:,\d{3})*원)|\s*\(?\d+\)?$|\s*/\s*무료배송|\s*/\s*무배', '', full_title).strip()
                deal_list.append({'thumbnail': thumbnail, 'source': '뽐뿌', 'author': author_cell.text.strip(), 'title': clean_title, 'price': price, 'shipping': shipping, 'link': link})
        except Exception: continue
    return deal_list

async def scrape_ruliweb():
    deal_list = []
    browser = None
    try:
        print("루리웹 크롤러 시작...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto('https://bbs.ruliweb.com/market/board/1020', timeout=20000)
            
            list_selector = 'table.board_list_table tbody tr.table_body'
            await page.wait_for_selector(list_selector, timeout=15000)
            
            posts = await page.query_selector_all(list_selector)

            for item in posts:
                try:
                    # 공지사항 건너뛰기
                    is_notice = await item.evaluate('(element) => element.classList.contains("notice")')
                    if is_notice:
                        continue

                    # 제목 및 링크
                    title_tag = await item.query_selector('a.deco')
                    if not title_tag:
                        continue
                    
                    full_title = (await title_tag.inner_text()).strip()
                    link = await title_tag.get_attribute('href')
                    
                    if link and link.startswith('/'):
                        link = 'https://bbs.ruliweb.com' + link
                    
                    # 작성자
                    author_tag = await item.query_selector('td.writer a')
                    author = (await author_tag.inner_text()).strip() if author_tag else "작성자 정보 없음"

                    # 썸네일 (목록에는 없음, 빈 문자열 반환)
                    thumbnail = ""

                    # 가격 추출
                    price_match = re.search(r'(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)', full_title)
                    price = price_match.group(1) if price_match else "가격 정보 없음"
                    
                    # 제목 정리
                    clean_title = re.sub(r'\[.*?\]|\s*\(\d+\)$|\s*\(?(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)\)?', '', full_title).strip()
                    
                    deal_list.append({
                        'thumbnail': thumbnail,
                        'source': '루리웹',
                        'author': author,
                        'title': clean_title,
                        'price': price,
                        'shipping': '정보 없음',
                        'link': link
                    })
                    
                except Exception as e:
                    print(f"루리웹 항목 파싱 오류: {e}")
                    continue
            
            print(f"루리웹 게시물 {len(deal_list)}개 처리 완료.")
            await browser.close()
            browser = None
            
    except Exception as e:
        print(f"루리웹 Playwright 크롤링 중 오류 발생: {e}")
        if browser:
            await browser.close()
        return []
    
    return deal_list



# --- API 엔드포인트 (Zod 제외) ---
@app.get('/api/hotdeals')
async def hotdeals(source: str = "all"):
    tasks = []
    if source == "ppomppu":
        tasks.append(scrape_ppomppu())
    elif source == "ruliweb":
        tasks.append(scrape_ruliweb())
    elif source == "zod":
        tasks.append(scrape_zod())  # Zod 크롤러 추가
    else:  # source == "all"
        tasks.extend([scrape_ppomppu(), scrape_ruliweb(), scrape_zod()])
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined_list = []
    for result in results:
        if not isinstance(result, Exception):
            combined_list.extend(result)
    return combined_list



@app.get("/image-proxy")
async def image_proxy(url: str, source: str = "뽐뿌"):
    referer_map = { 
        "뽐뿌": "https://www.ppomppu.co.kr/", 
        "루리웹": "https://bbs.ruliweb.com/",
        "Zod": "https://zod.kr/"
    }
    headers = { 'Referer': referer_map.get(source, "https://www.google.com/"), 'User-Agent': 'Mozilla/5.0' }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            media_type = response.headers.get('content-type', 'image/jpeg')
            return Response(content=response.content, media_type=media_type)
        except (httpx.RequestError, KeyError) as e:
            print(f"이미지 프록시 오류: {e} for URL {url}")
            return Response(status_code=404)


# templates_dir 정의 - 반드시 app.mount() 이전에 위치
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")


@app.get("/", response_class=FileResponse)
async def read_root():
    return os.path.join(templates_dir, "index.html")

app.mount("/", StaticFiles(directory=templates_dir, html=True), name="static")

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)