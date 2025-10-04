# app.py 전체를 이 코드로 교체하세요.

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
import requests
from bs4 import BeautifulSoup
import uvicorn
import asyncio
import os
import re
import httpx

app = FastAPI()

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    # ... (이전과 동일, 생략)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self';"
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com;"
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;"
        "font-src 'self' https://fonts.gstatic.com;"
        "img-src 'self' data: https:;"
        "connect-src 'self';"
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 개별 사이트 크롤링 함수 (루리웹 최종 업그레이드) ---

async def scrape_ppomppu():
    # ... (이전과 동일, 생략)
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
            author_cell = item.find('span', class_='baseList-name')
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
        except (AttributeError, KeyError, IndexError): continue
    return deal_list

async def fetch_ruliweb_thumbnail(session, post_url):
    """게시물 상세 페이지에 접속하여 첫 번째 이미지 URL을 가져오는 함수"""
    try:
        response = await session.get(post_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5.0)
        post_soup = BeautifulSoup(response.text, 'html.parser')
        # 본문 영역에서 첫 번째 이미지 태그를 찾습니다.
        img_tag = post_soup.select_one('div.view_content img')
        if img_tag and img_tag.get('src'):
            thumbnail_url = img_tag['src']
            if thumbnail_url.startswith('//'):
                return 'https:' + thumbnail_url
            return thumbnail_url
    except Exception:
        return "" # 오류 발생 시 빈 문자열 반환
    return ""

async def scrape_ruliweb():
    # 루리웹 크롤러를 2단계 심층 방식으로 업그레이드했습니다.
    list_url = 'https://bbs.ruliweb.com/market/board/1020'
    try:
        async with httpx.AsyncClient() as client:
            list_response = await client.get(list_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10.0)
            list_response.raise_for_status()
            
            list_soup = BeautifulSoup(list_response.text, 'html.parser')
            posts_data = []
            thumbnail_tasks = []

            # 1단계: 게시물 목록에서 기본 정보(링크, 제목 등) 수집
            for item in list_soup.select('tr.table_body.blocktarget'):
                if 'notice' in item.get('class', []): continue
                title_tag = item.select_one('a.deco')
                author_tag = item.select_one('td.writer a')
                if title_tag and author_tag:
                    post_link = title_tag['href']
                    posts_data.append({'link': post_link, 'author': author_tag.text.strip(), 'full_title': title_tag.text.strip()})
                    # 2단계(준비): 각 게시물의 썸네일을 가져올 작업을 리스트에 추가
                    thumbnail_tasks.append(fetch_ruliweb_thumbnail(client, post_link))

            # 2단계(실행): 모든 썸네일 가져오기 작업을 동시에 실행
            thumbnail_urls = await asyncio.gather(*thumbnail_tasks)
            
            deal_list = []
            # 3단계: 기본 정보와 썸네일 정보를 합쳐서 최종 데이터 생성
            for i, post in enumerate(posts_data):
                full_title = post['full_title']
                source = re.search(r'\[(.*?)\]', full_title).group(1) if re.search(r'\[(.*?)\]', full_title) else "기타"
                price_match = re.search(r'(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)', full_title)
                price = price_match.group(1) if price_match else "가격 정보 없음"
                clean_title = re.sub(r'\[.*?\]|\s*\(\d+\)$|\s*\(?(\d{1,3}(?:,\d{3})*원|\d+\.\d+\$)\)?', '', full_title).strip()
                
                deal_list.append({
                    'thumbnail': thumbnail_urls[i], # 가져온 썸네일 URL 사용
                    'source': '루리웹',
                    'author': post['author'],
                    'title': clean_title,
                    'price': price,
                    'shipping': '정보 없음',
                    'link': post['link']
                })
    except (httpx.RequestError, AttributeError, KeyError, IndexError):
        return []
    return deal_list

async def scrape_zod():
    # ... (이전과 동일, 생략)
    url = 'https://zod.kr/deal'
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10.0)
            response.raise_for_status()
    except httpx.RequestError: return []
    soup = BeautifulSoup(response.text, 'html.parser')
    deal_list = []
    for item in soup.select('a.deal-item'):
        try:
            title_tag = item.select_one('h3.deal-title')
            price_tag = item.select_one('span.deal-price')
            thumbnail_tag = item.select_one('div.deal-thumb img')
            if title_tag and price_tag:
                link = item['href']
                if not link.startswith('http'): link = 'https://zod.kr' + link
                thumbnail_src = thumbnail_tag.get('data-src') or thumbnail_tag.get('src', '')
                if thumbnail_src.startswith('//'): thumbnail = 'https:' + thumbnail_src
                else: thumbnail = thumbnail_src
                deal_list.append({'thumbnail': thumbnail, 'source': "조드", 'author': '정보 없음', 'title': title_tag.text.strip(), 'price': price_tag.text.strip(), 'shipping': '정보 없음', 'link': link})
        except (AttributeError, KeyError, IndexError): continue
    return deal_list

# (이하 API 엔드포인트 및 서버 실행 코드는 이전과 동일합니다)
@app.get('/api/hotdeals')
async def hotdeals(source: str = "all"):
    # ... (생략)
    tasks = []
    if source == "ppomppu": tasks.append(scrape_ppomppu())
    elif source == "ruliweb": tasks.append(scrape_ruliweb())
    elif source == "zod": tasks.append(scrape_zod())
    else: tasks.extend([scrape_ppomppu(), scrape_ruliweb(), scrape_zod()])
    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined_list = []
    for result in results:
        if not isinstance(result, Exception): combined_list.extend(result)
    return combined_list

@app.get("/image-proxy")
async def image_proxy(url: str, source: str = "뽐뿌"):
    # ... (생략)
    referer_map = { "뽐뿌": "https://www.ppomppu.co.kr/", "루리웹": "https://bbs.ruliweb.com/", "조드": "https://zod.kr/" }
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

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

@app.get("/", response_class=FileResponse)
async def read_root():
    # ... (생략)
    return os.path.join(templates_dir, "index.html")

app.mount("/", StaticFiles(directory=templates_dir, html=True), name="static")

if __name__ == '__main__':
    # ... (생략)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)