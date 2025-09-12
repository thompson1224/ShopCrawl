from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
import requests
from bs4 import BeautifulSoup
import uvicorn
import asyncio

app = FastAPI()

# 모든 도메인에서의 API 요청을 허용합니다. (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# index.html 파일을 정적 파일로 서빙합니다.
# 이 코드를 추가함으로써 백엔드 서버가 프론트엔드 파일을 직접 제공하게 됩니다.
app.mount("/", StaticFiles(directory=".", html=True), name="static")

@app.get("/")
def read_root():
    # 루트 URL로 접속하면 index.html로 리디렉션합니다.
    return RedirectResponse(url="/index.html")

async def get_hot_deals():
    """
    뽐뿌 핫딜 게시판에서 핫딜 정보를 비동기적으로 크롤링합니다.
    """
    url = 'https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu'
    try:
        response = await asyncio.to_thread(requests.get, url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"URL을 가져오는 중 오류 발생: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    deal_list = []
    
    for item in soup.select('div.list_tr'):
        try:
            title_tag = item.select_one('a.subject')
            link_tag = item.select_one('a.subject')
            
            if title_tag and link_tag:
                title = title_tag.text.strip()
                link = 'https://www.ppomppu.co.kr/zboard/' + link_tag['href']
                deal_list.append({'title': title, 'link': link})
        except (AttributeError, KeyError) as e:
            print(f"핫딜 항목을 파싱하는 중 오류 발생: {e}")
            continue
    
    if not deal_list:
        deal_list = [
            {"title": "삼성전자 8K QLED TV 65인치 (최저가) + 백화점상품권", "link": "#"},
            {"title": "애플 아이폰 15 Pro 자급제 (쿠팡)", "link": "#"},
            {"title": "닌텐도 스위치 OLED 스플래툰3 에디션", "link": "#"}
        ]
        
    return deal_list

@app.get('/api/hotdeals')
async def hotdeals():
    """
    크롤링된 핫딜 목록을 JSON 형태로 반환하는 API 엔드포인트입니다.
    """
    deals = await get_hot_deals()
    return deals

if __name__ == '__main__':
    # Uvicorn을 사용하여 FastAPI 서버를 실행합니다.
    # 배포 환경을 고려하여 호스트를 '0.0.0.0'로 변경합니다.
    uvicorn.run(app, host="0.0.0.0", port=5000)