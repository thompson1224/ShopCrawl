from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse  # RedirectResponse 대신 FileResponse 사용
import requests
from bs4 import BeautifulSoup
import uvicorn
import asyncio
import os

app = FastAPI()

# CORS 미들웨어 설정 (기존과 동일)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 순서 변경 ---
# 1. API 라우트를 먼저 정의합니다.
@app.get('/api/hotdeals')
async def hotdeals():
    """
    크롤링된 핫딜 목록을 JSON 형태로 반환하는 API 엔드포인트입니다.
    """
    deals = await get_hot_deals()
    return deals

# (get_hot_deals 함수는 여기에 그대로 둡니다)
async def get_hot_deals():
    # ... (기존 코드와 동일)
    url = 'https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu'
    try:
        response = await asyncio.to_thread(requests.get, url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"URL을 가져오는 중 오류 발생: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    deal_list = []
    
    # 뽐뿌의 새로운 구조에 맞춰 선택자를 수정합니다. 
    # 'div.list_tr' 대신 'tr.list_vspace'를 사용하고, 제목과 링크 선택자도 수정합니다.
    base_url = "https://www.ppomppu.co.kr/zboard/"
    for item in soup.find_all('tr', class_='list_vspace'):
        try:
            # 제목과 링크가 포함된 a 태그를 찾습니다.
            title_tag = item.find('a', href=lambda href: href and "view.php" in href)
            
            if title_tag:
                title = title_tag.get_text(strip=True)
                link = base_url + title_tag['href']
                
                # 불필요한 이미지 태그 등 제거
                for img in title_tag.find_all('img'):
                    img.decompose()
                title = title_tag.get_text(strip=True)

                if title: # 제목이 비어있지 않은 경우에만 추가
                    deal_list.append({'title': title, 'link': link})

        except (AttributeError, KeyError) as e:
            print(f"핫딜 항목을 파싱하는 중 오류 발생: {e}")
            continue

    if not deal_list:
        print("크롤링된 핫딜이 없습니다. 임시 데이터를 반환합니다.")
        return [
            {"title": "크롤링 실패! 임시 데이터: 삼성 TV", "link": "#"},
            {"title": "크롤링 실패! 임시 데이터: 아이폰 15 Pro", "link": "#"},
        ]
        
    return deal_list

# 2. 정적 파일 마운트를 나중에 설정합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
app.mount("/", StaticFiles(directory=templates_dir, html=True), name="static")

# 루트 경로 핸들러는 StaticFiles가 처리하므로 불필요할 수 있습니다.
# 만약 특정 동작이 필요하다면 유지할 수 있지만, 지금 구조에서는 StaticFiles가
# 자동으로 index.html을 찾아주므로 아래 코드는 제거해도 괜찮습니다.
# @app.get("/")
# def read_root():
#     return FileResponse(os.path.join(templates_dir, "index.html"))

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=5000, reload=True)