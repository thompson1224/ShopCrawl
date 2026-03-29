from fastapi import FastAPI, Request, Depends, Header, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy import desc
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_current_user_required,
    get_db,
    decode_token,
)
from models import User
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy import or_

import uvicorn
import asyncio
import os
import re
import time
import httpx
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from models import (
    HotDeal,
    RuliwebThumbnail,
    SessionLocal,
    Comment,
    TelegramUser,
    classify_category,
)
from datetime import datetime, timedelta
import logging
import pytz
import shutil
import secrets
import hashlib
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import google.generativeai as genai
from urllib.parse import urlparse


# 환경변수 로드 (선택)
from dotenv import load_dotenv

load_dotenv()


# LLM 관련 키
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IS_PRODUCTION = os.getenv("APP_ENV") == "production"
CHROMA_DB_DIR = "/data/chroma_db" if IS_PRODUCTION else "./chroma_db"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# PORT 설정 (없으면 8000)
PORT = int(os.getenv("PORT", 8000))

# 네이버 로그인 콜백 URL
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
if IS_PRODUCTION:
    BASE_URL = os.getenv("BASE_URL", "https://www.dealcat.co.kr")
else:
    BASE_URL = "http://localhost:8000"
NAVER_CALLBACK_URL = f"{BASE_URL}/api/auth/naver/callback"
COOKIE_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60
NAVER_STATE_COOKIE = "naver_oauth_state"
ACCESS_TOKEN_COOKIE = "access_token"
ALLOWED_IMAGE_HOST_SUFFIXES = {
    "뽐뿌": {"ppomppu.co.kr"},
    "루리웹": {"ruliweb.com"},
    "Zod": {"zod.kr"},
    "어미새": {"eomisae.co.kr"},
    "퀘이사존": {"quasarzone.com"},
}

# # 네이버 설정
# NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
# NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
# NAVER_CALLBACK_URL = "http://localhost:8000/api/auth/naver/callback"

# if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
#     print("⚠️ 경고: 네이버 로그인 키가 설정되지 않았습니다!")


# 로깅 설정 (구조화된 JSON 로그)
import json


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_data, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
root_logger = logging.getLogger()
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# /api/hotdeals 인메모리 캐시 (30초 TTL)
_hotdeals_cache: dict = {}
CACHE_TTL = 30

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
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self';"
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[BASE_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"],
)


def is_valid_admin_secret(candidate: str | None) -> bool:
    return (
        bool(ADMIN_SECRET)
        and bool(candidate)
        and secrets.compare_digest(candidate, ADMIN_SECRET)
    )


def require_admin_access(secret: str = "", x_admin_secret: str | None = None) -> None:
    provided_secret = x_admin_secret or secret
    if not is_valid_admin_secret(provided_secret):
        raise HTTPException(status_code=403, detail="관리자 인증이 필요합니다")


def is_allowed_image_url(raw_url: str, source: str) -> bool:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").lower()
    if not hostname or parsed.username or parsed.password:
        return False

    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return False

    allowed_suffixes = ALLOWED_IMAGE_HOST_SUFFIXES.get(source)
    if not allowed_suffixes:
        return False

    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in allowed_suffixes
    )


def make_rag_id(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def make_rag_document(deal: dict) -> Document:
    return Document(
        page_content=f"[{deal['source']}] {deal['title']} - 가격: {deal['price']}",
        metadata={
            "link": deal["link"],
            "source": deal["source"],
            "price": deal["price"],
            "rag_id": make_rag_id(deal["link"]),
        },
    )


def upsert_rag_documents(vectorstore: Chroma, documents: list[Document]) -> None:
    if not documents:
        return

    ids = [doc.metadata["rag_id"] for doc in documents]
    vectorstore.delete(ids=ids)
    vectorstore.add_documents(documents, ids=ids)


# 가격 추출 헬퍼 (여러 형식 지원)
def extract_price(text):
    patterns = [
        r"(\d{1,3}(?:,\d{3})*원(?:대)?)",  # 1,500원, 1,500원대
        r"(₩\s*\d{1,3}(?:,\d{3})+)",  # ₩143,624 / ₩ 10,150
        r"(\d+\.?\d*만\s*원(?:대)?)",  # 1.9만원, 5만원대
        r"(\d{4,6}원)",  # 5500원
        r"(\d{1,3}(?:,\d{3})+)(?!\d|%)",  # 49,900 (원 없는 콤마 구분 숫자, % 제외)
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return "가격 정보 없음"


def clean_deal_title(title: str) -> str:
    """핫딜 제목에서 의미없는 텍스트 제거"""
    if not title:
        return ""

    cleaned = title

    patterns_to_remove = [
        r"\[.*?\]",  # [사이트명], [분류] 등
        r"\s*\([^)]*\)",  # (내용), (123원), (할인) 등 괄호 안 전체
        r"\s*/\s*무료배송",  # /무료배송
        r"\s*/\s*무배",  # /무배
        r"\s*/\s*무료\s*",  # /무료 (뒤에 내용이 있는 경우)
        r"\s*/\s*\d+원?",  # /3000원 같은运费비 표시
        r"\s*\|\s*.*$",  # | 이후 모든 내용
        r"\s*&\s*.*$",  # & 이후 모든 내용
        r"\s*=\s*.*$",  # = 이후 모든 내용
        r"\d{1,3}(?:,\d{3})*원\s*$",  # 끝에 있는 가격 (10,000원)
        r"\d+만\s*원\s*$",  # 끝에 있는 만원 (5만원)
        r"^\s*\d+\s*$",  # 숫자만 있는 경우
        r"^\s*-\s*",  # 시작의 -
    ]

    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned)  # 여러 공백을 하나로
    cleaned = re.sub(r"^[\s\-–—\.]+|[\s\-–—\.]+$", "", cleaned)  # 앞뒤 특수문자 제거

    return cleaned.strip()


# 크롤링 함수들
async def scrape_ppomppu():
    logger.info("뽐뿌 크롤링 시작")
    url = "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0
            )
            response.raise_for_status()
    except httpx.RequestError:
        logger.error("뽐뿌 크롤링 실패")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    deal_list = []
    base_url = "https://www.ppomppu.co.kr/zboard/"
    main_table = soup.find("table", id="revolution_main_table")
    if not main_table:
        return []

    for item in main_table.find_all("tr", class_="baseList"):
        try:
            title_cell = item.find("td", class_="title")
            author_cell = item.find("span", "baseList-name")
            if not (title_cell and author_cell):
                continue
            title_tag = title_cell.find("a", class_="baseList-title")
            if title_tag and "id=ppomppu" in title_tag["href"]:
                full_title = title_tag.get_text(strip=True)
                link = (
                    base_url + title_tag["href"]
                    if title_tag["href"].startswith("view.php")
                    else title_tag["href"]
                )
                thumbnail_tag = title_cell.find("img")
                thumbnail_src = thumbnail_tag["src"] if thumbnail_tag else ""
                if thumbnail_src.startswith("//"):
                    thumbnail = "https:" + thumbnail_src
                else:
                    thumbnail = thumbnail_src
                source = (
                    re.search(r"\[(.*?)\]", full_title).group(1)
                    if re.search(r"\[(.*?)\]", full_title)
                    else "기타"
                )
                price_match = re.search(r"(\d{1,3}(?:,\d{3})*원)", full_title)
                price = price_match.group(1) if price_match else "가격 정보 없음"
                shipping = (
                    "무료배송"
                    if "무료" in full_title or "무배" in full_title
                    else "배송비 정보 없음"
                )
                clean_title = clean_deal_title(full_title)
                category = classify_category(clean_title)
                deal_list.append(
                    {
                        "thumbnail": thumbnail,
                        "source": "뽐뿌",
                        "author": author_cell.text.strip(),
                        "title": clean_title,
                        "price": price,
                        "shipping": shipping,
                        "link": link,
                        "category": category,
                    }
                )
        except Exception:
            continue

    logger.info(f"뽐뿌 크롤링 완료: {len(deal_list)}개")
    return deal_list


async def scrape_ruliweb():
    logger.info("루리웹 크롤링 시작")
    deal_list = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(
                "https://bbs.ruliweb.com/market/board/1020", timeout=15.0
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("table.board_list_table tbody tr.table_body")

            for row in rows:
                try:
                    if "notice" in row.get("class", []):
                        continue

                    title_tag = row.select_one("a.deco")
                    if not title_tag:
                        continue

                    full_title = title_tag.get_text(strip=True)
                    link = title_tag.get("href", "")
                    if link.startswith("/"):
                        link = "https://bbs.ruliweb.com" + link

                    author_tag = row.select_one("td.writer a")
                    author = author_tag.get_text(strip=True) if author_tag else "작성자"

                    price = extract_price(full_title)
                    clean_title = clean_deal_title(full_title)
                    category = classify_category(clean_title)

                    deal_list.append(
                        {
                            "thumbnail": "",
                            "source": "루리웹",
                            "author": author,
                            "title": clean_title,
                            "price": price,
                            "shipping": "정보 없음",
                            "link": link,
                            "category": category,
                        }
                    )
                except Exception:
                    continue

            # 개별 포스트에서 og:image 병렬 fetch (semaphore로 동시 5개 제한)
            # DB 캐싱: 기존에 가져온 썸네일이 있으면 사용, 없으면 fetch 후 저장
            db = SessionLocal()
            cached_thumbnails = {}
            links_to_fetch = []

            try:
                cached = (
                    db.query(RuliwebThumbnail)
                    .filter(RuliwebThumbnail.link.in_([d["link"] for d in deal_list]))
                    .all()
                )
                cached_thumbnails = {c.link: c.thumbnail_url for c in cached}

                for deal in deal_list:
                    if deal["link"] in cached_thumbnails:
                        deal["thumbnail"] = cached_thumbnails[deal["link"]]
                    else:
                        links_to_fetch.append(deal["link"])
            except Exception as e:
                logger.warning(f"루리웹 썸네일 캐시 조회 오류: {e}")
                links_to_fetch = [d["link"] for d in deal_list]
            finally:
                db.close()

            sem = asyncio.Semaphore(5)

            async def fetch_og_image(url):
                async with sem:
                    try:
                        r = await client.get(url, timeout=5.0)
                        s = BeautifulSoup(r.text, "html.parser")
                        og = s.find("meta", property="og:image")
                        return og.get("content", "") if og else ""
                    except Exception:
                        return ""

            if links_to_fetch:
                thumbnails = await asyncio.gather(
                    *[
                        fetch_og_image(d["link"])
                        for d in deal_list
                        if d["link"] in links_to_fetch
                    ]
                )
                new_cached = []
                for deal, thumb in zip(deal_list, thumbnails):
                    if deal["link"] in links_to_fetch:
                        deal["thumbnail"] = thumb
                        if thumb:
                            new_cached.append(
                                RuliwebThumbnail(
                                    link=deal["link"],
                                    thumbnail_url=thumb,
                                    fetched_at=datetime.now(KST).replace(tzinfo=None),
                                )
                            )

                if new_cached:
                    db = SessionLocal()
                    try:
                        for cached in new_cached:
                            existing = (
                                db.query(RuliwebThumbnail)
                                .filter(RuliwebThumbnail.link == cached.link)
                                .first()
                            )
                            if not existing:
                                db.add(cached)
                        db.commit()
                    except Exception as e:
                        logger.warning(f"루리웹 썸네일 캐시 저장 오류: {e}")
                        db.rollback()
                    finally:
                        db.close()

    except Exception as e:
        logger.error(f"루리웹 크롤링 오류: {e}")

    logger.info(f"루리웹 크롤링 완료: {len(deal_list)}개")
    return deal_list


async def scrape_zod():
    logger.info("Zod 크롤링 시작")
    deal_list = []
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession(impersonate="chrome120") as session:
            response = await session.get(
                "https://zod.kr/deal",
                headers={
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
                timeout=15,
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select("ul.app-board-template-list li")

        for item in posts:
            try:
                text_content = item.get_text()
                if not text_content or "공지" in text_content[:10]:
                    continue

                link_tag = item.select_one('a[href*="/deal/"]')
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                if not href or "/deal/" not in href:
                    continue
                link = "https://zod.kr" + href if href.startswith("/") else href

                img = item.select_one("img")
                thumbnail = ""
                if img:
                    src = img.get("src", "")
                    if src.startswith("//"):
                        thumbnail = "https:" + src
                    elif src.startswith("http"):
                        thumbnail = src

                title_span = item.select_one("span.app-list-title-item")
                title = title_span.get_text(strip=True) if title_span else "제목 없음"

                # 가격/배송비: dl.zod-board--deal-meta > dd 순회
                price = "가격 정보 없음"
                shipping = "정보 없음"
                for dd in item.select("dl.zod-board--deal-meta dd"):
                    dd_text = dd.get_text(strip=True)
                    strong = dd.select_one("strong")
                    if not strong:
                        continue
                    val = strong.get_text(strip=True)
                    if "가격:" in dd_text:
                        price = val
                    elif "배송비:" in dd_text:
                        shipping = "무료배송" if "무료" in val else val

                member_div = item.select_one("dd.app-list-member")
                author = "작성자"
                if member_div:
                    # img 태그 제거 후 텍스트만
                    for img in member_div.find_all("img"):
                        img.decompose()
                    author = member_div.get_text(strip=True) or "작성자"

                deal_list.append(
                    {
                        "thumbnail": thumbnail,
                        "source": "Zod",
                        "author": author,
                        "title": clean_deal_title(title),
                        "price": price,
                        "shipping": shipping,
                        "link": link,
                        "category": classify_category(title),
                    }
                )
            except Exception:
                continue

    except Exception as e:
        logger.error(f"Zod 크롤링 오류: {e}")

    logger.info(f"Zod 크롤링 완료: {len(deal_list)}개")
    return deal_list


# 퀘이사존 크롤
async def scrape_quasarzone():
    logger.info("퀘이사존 크롤링 시작")
    deal_list = []

    try:
        # httpx로 간단하게 크롤링 (정적 HTML)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://quasarzone.com/bbs/qb_saleinfo",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": "https://quasarzone.com",
                },
                timeout=15.0,
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        logger.info(f"퀘이사존 HTML 길이: {len(response.text)}")

        # 게시글 리스트 찾기
        posts = soup.find_all("div", class_="market-info-list")
        logger.info(f"퀘이사존: {len(posts)}개 게시글 발견")

        for idx, item in enumerate(posts[:20]):  # 최대 20개
            try:
                # 썸네일
                thumbnail = ""
                thumb_wrap = item.find("div", class_="thumb-wrap")
                if thumb_wrap:
                    img_tag = thumb_wrap.find("img", class_="maxImg")
                    if img_tag and img_tag.get("src"):
                        thumbnail_src = img_tag["src"]
                        if thumbnail_src.startswith("//"):
                            thumbnail = "https:" + thumbnail_src
                        elif thumbnail_src.startswith("http"):
                            thumbnail = thumbnail_src
                        elif thumbnail_src.startswith("/"):
                            thumbnail = "https://quasarzone.com" + thumbnail_src

                # 제목 및 링크
                cont = item.find("div", class_="market-info-list-cont")
                if not cont:
                    continue

                tit = cont.find("p", class_="tit")
                if not tit:
                    continue

                link_tag = tit.find("a", class_="subject-link")
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href = link_tag.get("href", "")

                if href.startswith("/"):
                    link = "https://quasarzone.com" + href
                elif href.startswith("http"):
                    link = href
                else:
                    link = "https://quasarzone.com/" + href

                # 작성자
                author = "작성자"
                nick_wrap = cont.find("span", class_="nick")
                if nick_wrap:
                    author = nick_wrap.get_text(strip=True)

                # 가격: span.text-orange (￦ 59,000 (KRW) 형식)
                price = "가격 정보 없음"
                price_el = cont.select_one("span.text-orange")
                if price_el:
                    raw = price_el.get_text(strip=True)  # "￦ 59,000 (KRW)"
                    price_match = re.search(r"[\d,]+", raw)
                    if price_match:
                        price = price_match.group(0) + "원"
                else:
                    price_match = re.search(r"(\d{1,3}(?:,\d{3})*원)", title)
                    if price_match:
                        price = price_match.group(1)

                # 배송비
                shipping_el = cont.select_one(
                    "div.market-info-sub span:not(.category):not(.text-orange):not(.nick):not(.count):not(.date)"
                )
                shipping_text = shipping_el.get_text(strip=True) if shipping_el else ""
                if "무료" in title + shipping_text or "무배" in title + shipping_text:
                    shipping = "무료배송"
                elif shipping_text and "배송" in shipping_text:
                    shipping = shipping_text
                else:
                    shipping = "정보 없음"

                deal_list.append(
                    {
                        "thumbnail": thumbnail,
                        "source": "퀘이사존",
                        "author": author,
                        "title": clean_deal_title(title),
                        "price": price,
                        "shipping": shipping,
                        "link": link,
                        "category": classify_category(title),
                    }
                )

                logger.debug(f"퀘이사존 항목 {idx + 1}: {title[:30]}...")

            except Exception as e:
                logger.warning(f"퀘이사존 항목 {idx + 1} 파싱 오류: {e}")
                continue

    except Exception as e:
        logger.error(f"퀘이사존 크롤링 전체 오류: {e}")

    logger.info(f"퀘이사존 크롤링 완료: {len(deal_list)}개")
    return deal_list


# 어미새 크롤
async def scrape_eomisae():
    logger.info("어미새 크롤링 시작")
    deal_list = []
    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
        ) as client:
            response = await client.get("https://eomisae.co.kr/fs", timeout=20.0)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select(".card_el")

        if not items:
            logger.warning("어미새: .card_el 셀렉터 결과 없음")
            return []

        for idx, item in enumerate(items[:20]):
            try:
                link_tag = item.select_one("a")
                if not link_tag:
                    continue
                link_href = link_tag.get("href", "")
                if not link_href:
                    continue
                if link_href.startswith("/"):
                    link = "https://eomisae.co.kr" + link_href
                elif link_href.startswith("http"):
                    link = link_href
                else:
                    continue

                title_tag = item.select_one("h3") or item.select_one("h2")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title or title == "list_adsense":
                    continue

                img_tag = item.select_one("img")
                thumbnail = ""
                if img_tag:
                    src = img_tag.get("src", "")
                    if src.startswith("//"):
                        thumbnail = "https:" + src
                    elif src.startswith("http"):
                        thumbnail = src
                    elif src.startswith("/"):
                        thumbnail = "https://eomisae.co.kr" + src

                price = extract_price(title)
                shipping = (
                    "무료배송" if "무료" in title or "무배" in title else "정보 없음"
                )

                deal_list.append(
                    {
                        "thumbnail": thumbnail,
                        "source": "어미새",
                        "author": "작성자",
                        "title": clean_deal_title(title),
                        "price": price,
                        "shipping": shipping,
                        "link": link,
                        "category": classify_category(title),
                    }
                )

            except Exception as e:
                logger.warning(f"어미새 항목 {idx + 1} 파싱 오류: {e}")
                continue

    except Exception as e:
        logger.error(f"어미새 크롤링 오류: {e}")

    logger.info(f"어미새 크롤링 완료: {len(deal_list)}개")
    return deal_list


# models.py에도 추가
KST = pytz.timezone("Asia/Seoul")


async def crawl_and_save_to_db():
    logger.info(
        f"=== 백그라운드 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
    )

    all_deals = []

    # --- 전체 5개 사이트 병렬 실행 ---
    logger.info("--- 크롤러 5개 병렬 시작 ---")
    tasks = [
        scrape_ppomppu(),
        scrape_quasarzone(),
        scrape_ruliweb(),
        scrape_eomisae(),
        scrape_zod(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"크롤링 오류: {result}")
        else:
            all_deals.extend(result)
    logger.info("--- 크롤러 5개 완료 ---")

    # --- 3. DB 및 벡터 DB 저장 ---
    if not all_deals:
        return

    db = SessionLocal()
    new_count = 0
    duplicate_count = 0

    # RAG(벡터DB)에 추가/갱신할 문서 리스트
    deals_for_rag = []

    try:
        for deal in all_deals:
            try:
                existing = (
                    db.query(HotDeal).filter(HotDeal.link == deal["link"]).first()
                )

                if existing:
                    changed = (
                        existing.title != deal["title"]
                        or existing.price != deal["price"]
                        or existing.shipping != deal["shipping"]
                        or existing.thumbnail != deal["thumbnail"]
                        or existing.category != deal.get("category", "기타")
                    )
                    existing.title = deal["title"]
                    existing.price = deal["price"]
                    existing.shipping = deal["shipping"]
                    existing.thumbnail = deal["thumbnail"]
                    existing.category = deal.get("category", "기타")
                    duplicate_count += 1
                    if changed:
                        deals_for_rag.append(make_rag_document(deal))
                else:
                    db_deal = HotDeal(
                        **deal, created_at=datetime.now(KST).replace(tzinfo=None)
                    )
                    db.add(db_deal)
                    new_count += 1
                    deals_for_rag.append(make_rag_document(deal))

                db.flush()
            except Exception:
                continue

        db.commit()

        # --- 4. 벡터 DB(Chroma)에 신규 데이터 추가 ---
        if deals_for_rag and GOOGLE_API_KEY:
            try:
                vectorstore = get_vectorstore()
                if vectorstore:
                    upsert_rag_documents(vectorstore, deals_for_rag)
                    logger.info(
                        f"🧠 RAG: 핫딜 {len(deals_for_rag)}개를 Gemini 기억장치에 동기화했습니다."
                    )
            except Exception as rag_error:
                logger.error(f"🧠 RAG 저장 실패: {rag_error}")

        total_count = db.query(HotDeal).count()
        logger.info(f"✅ DB 저장 완료: 신규 {new_count}, 전체 {total_count}")
        if new_count > 0:
            _hotdeals_cache.clear()

    except Exception as e:
        logger.error(f"❌ DB 저장 오류: {e}")
        db.rollback()
    finally:
        db.close()


def backup_database():
    """DB 백업 (Railway Volume 내부에 저장)"""
    if IS_PRODUCTION:
        db_path = "/data/hotdeals.db"
        backup_dir = "/data/backups"

        # 백업 디렉토리 생성
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        backup_path = f"{backup_dir}/hotdeals_backup_{timestamp}.db"

        try:
            shutil.copy2(db_path, backup_path)
            logger.info(f"✅ DB 백업 완료: {backup_path}")

            # 오래된 백업 삭제 (최근 7개만 유지)
            backups = sorted(
                [f for f in os.listdir(backup_dir) if f.startswith("hotdeals_backup_")],
                reverse=True,
            )
            for old_backup in backups[7:]:
                old_path = os.path.join(backup_dir, old_backup)
                os.remove(old_path)
                logger.info(f"🗑️ 오래된 백업 삭제: {old_backup}")

        except Exception as e:
            logger.error(f"❌ DB 백업 실패: {e}")

        # ChromaDB 백업
        chroma_backup_path = f"{backup_dir}/chroma_backup_{timestamp}"
        try:
            if os.path.exists(CHROMA_DB_DIR):
                if os.path.exists(chroma_backup_path):
                    shutil.rmtree(chroma_backup_path)
                shutil.copytree(CHROMA_DB_DIR, chroma_backup_path)
                logger.info(f"✅ ChromaDB 백업 완료: {chroma_backup_path}")

                # 오래된 ChromaDB 백업 삭제 (최근 7개만 유지)
                chroma_backups = sorted(
                    [
                        f
                        for f in os.listdir(backup_dir)
                        if f.startswith("chroma_backup_")
                    ],
                    reverse=True,
                )
                for old_backup in chroma_backups[7:]:
                    old_path = os.path.join(backup_dir, old_backup)
                    shutil.rmtree(old_path)
                    logger.info(f"🗑️ 오래된 ChromaDB 백업 삭제: {old_backup}")
        except Exception as e:
            logger.error(f"❌ ChromaDB 백업 실패: {e}")
    else:
        logger.info("⏭️ 로컬 환경: DB 백업 스킵")


def cleanup_old_deals():
    """30일 이상된 핫딜 및 ChromaDB orphan vectors 정리"""
    import chromadb
    from chromadb.config import Settings

    CLEANUP_DAYS = int(os.getenv("CLEANUP_DAYS", 30))
    cutoff_date = datetime.now(KST) - timedelta(days=CLEANUP_DAYS)
    cutoff_naive = cutoff_date.replace(tzinfo=None)

    logger.info(
        f"🧹 DB 정리 시작: {CLEANUP_DAYS}일 이전 데이터 삭제 (기준: {cutoff_date.strftime('%Y-%m-%d %H:%M')})"
    )

    db = SessionLocal()
    deleted_count = 0
    deleted_links = []

    try:
        old_deals = db.query(HotDeal).filter(HotDeal.created_at < cutoff_naive).all()
        deleted_count = len(old_deals)
        deleted_links = [deal.link for deal in old_deals]

        for deal in old_deals:
            db.delete(deal)

        db.commit()
        logger.info(f"🗑️ DB 정리 완료: {deleted_count}개 삭제")

    except Exception as e:
        logger.error(f"❌ DB 정리 오류: {e}")
        db.rollback()
    finally:
        db.close()

    if deleted_links and GOOGLE_API_KEY and IS_PRODUCTION:
        try:
            vectorstore = get_vectorstore()
            if vectorstore:
                rag_ids_to_delete = [make_rag_id(link) for link in deleted_links]
                vectorstore.delete(ids=rag_ids_to_delete)
                logger.info(
                    f"🧠 ChromaDB 정리: {len(rag_ids_to_delete)}개 orphan vectors 삭제"
                )
        except Exception as e:
            logger.error(f"❌ ChromaDB 정리 오류: {e}")


# Vector store
def get_vectorstore():
    """벡터 DB(기억장치) 가져오기 - Gemini 버전"""
    if not GOOGLE_API_KEY:
        return None

    # 구글의 무료 임베딩 모델 사용
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004", google_api_key=GOOGLE_API_KEY
    )

    vectorstore = Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings,
        collection_name="hotdeals",
    )
    return vectorstore


# 스케줄러 설정
scheduler = AsyncIOScheduler()


# FastAPI 이벤트 핸들러
# FastAPI 이벤트 핸들러
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 서버 시작: 백그라운드 스케줄러 활성화")

    # 서버 시작 후 5초 뒤 첫 크롤링 (Railway 헬스체크 통과 위해)
    scheduler.add_job(
        crawl_and_save_to_db,
        "date",
        run_date=datetime.now(KST) + timedelta(seconds=5),
        id="first_crawl",
        timezone=KST,
    )

    # 1분마다 크롤링 스케줄
    scheduler.add_job(
        crawl_and_save_to_db, "interval", minutes=5, id="crawl_job", timezone=KST
    )

    # 매일 새벽 3시 DB 백업
    scheduler.add_job(
        backup_database, "cron", hour=3, minute=0, id="backup_job", timezone=KST
    )

    # 매일 새벽 4시 30일 이상된 데이터 정리
    scheduler.add_job(
        cleanup_old_deals, "cron", hour=4, minute=0, id="cleanup_job", timezone=KST
    )

    scheduler.start()
    logger.info("⏰ 서버 시작 5초 후 첫 크롤링, 이후 5분마다 자동 크롤링")
    logger.info("💾 매일 새벽 3시 DB 자동 백업 활성화")
    logger.info("🧹 매일 새벽 4시 30일 이상된 데이터 자동 정리")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 서버 종료: 스케줄러 정지")
    scheduler.shutdown()


def parse_price_to_number(price_str: str) -> int:
    """가격 문자열을 숫자로 변환"""
    if not price_str or price_str == "가격 정보 없음":
        return 0
    numbers = re.findall(
        r"[\d,]+", price_str.replace("원", "").replace("₩", "").replace(" ", "")
    )
    if numbers:
        try:
            return int(numbers[0].replace(",", ""))
        except ValueError:
            return 0
    return 0


@app.get("/api/hotdeals")
async def hotdeals(
    source: str = "all",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    price_range: str = Query(
        default="all", regex="^(all|0-5만|5-10만|10-20만|20만\\+)$"
    ),
    category: str = "all",
    shipping_free: bool = False,
    sort: str = Query(default="latest", regex="^(latest|oldest)$"),
    db: Session = Depends(get_db),
):
    cache_key = (
        f"{source}:{page}:{per_page}:{price_range}:{category}:{shipping_free}:{sort}"
    )
    now = time.time()
    if cache_key in _hotdeals_cache:
        ts, cached = _hotdeals_cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached

    query = db.query(HotDeal)

    if source != "all":
        query = query.filter(HotDeal.source == source)

    if category != "all":
        query = query.filter(HotDeal.category == category)

    if shipping_free:
        query = query.filter(HotDeal.shipping.like("%무료%"))

    all_deals = query.all()

    if price_range != "all":
        filtered_deals = []
        for deal in all_deals:
            price_num = parse_price_to_number(deal.price)
            if price_range == "0-5만" and 0 < price_num <= 50000:
                filtered_deals.append(deal)
            elif price_range == "5-10만" and 50000 < price_num <= 100000:
                filtered_deals.append(deal)
            elif price_range == "10-20만" and 100000 < price_num <= 200000:
                filtered_deals.append(deal)
            elif price_range == "20만+" and price_num > 200000:
                filtered_deals.append(deal)
        all_deals = filtered_deals
        total = len(all_deals)
    else:
        total = len(all_deals)

    if sort == "oldest":
        all_deals.sort(key=lambda x: x.created_at)
    else:
        all_deals.sort(key=lambda x: x.created_at, reverse=True)

    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    paginated_deals = all_deals[offset : offset + per_page]

    logger.info(
        f"API 요청: source={source}, page={page}/{total_pages}, price_range={price_range}, shipping_free={shipping_free}, sort={sort} - {len(paginated_deals)}개 반환"
    )

    result = {
        "deals": [deal.to_dict() for deal in paginated_deals],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }
    _hotdeals_cache[cache_key] = (now, result)
    return result


# 전체 통계 API (선택)
@app.get("/api/stats")
async def stats(db: Session = Depends(get_db)):
    total = db.query(HotDeal).count()
    ppomppu_count = db.query(HotDeal).filter(HotDeal.source == "뽐뿌").count()
    ruliweb_count = db.query(HotDeal).filter(HotDeal.source == "루리웹").count()
    zod_count = db.query(HotDeal).filter(HotDeal.source == "Zod").count()
    eomisae_count = db.query(HotDeal).filter(HotDeal.source == "어미새").count()
    quasarzone_count = db.query(HotDeal).filter(HotDeal.source == "퀘이사존").count()

    return {
        "total": total,
        "ppomppu": ppomppu_count,
        "ruliweb": ruliweb_count,
        "zod": zod_count,
        "eomisae": eomisae_count,
        "quasarzone": quasarzone_count,
    }


# 카테고리 목록 API
@app.get("/api/categories")
async def categories():
    return {
        "categories": [
            {"id": "가전/디지털", "name": "가전/디지털", "icon": "📱"},
            {"id": "신세계/아웃렛", "name": "신세계/아웃렛", "icon": "👟"},
            {"id": "뷰티/화장품", "name": "뷰티/화장품", "icon": "💄"},
            {"id": "식품/건강", "name": "식품/건강", "icon": "🍎"},
            {"id": "가구/인테리어", "name": "가구/인테리어", "icon": "🏠"},
            {"id": "게임/취미", "name": "게임/취미", "icon": "🎮"},
            {"id": "기타", "name": "기타", "icon": "📦"},
        ]
    }


# 검색 API (FTS5)
@app.get("/api/search")
async def search(
    q: str = Query(default="", min_length=1),
    category: str = "all",
    price_range: str = Query(
        default="all", regex="^(all|0-5만|5-10만|10-20만|20만\\+)$"
    ),
    shipping_free: bool = False,
    sort: str = Query(default="latest", regex="^(latest|oldest)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text

    query = db.query(HotDeal)

    if q:
        query = query.filter(HotDeal.title.like(f"%{q}%"))

    if category != "all":
        query = query.filter(HotDeal.category == category)

    if shipping_free:
        query = query.filter(HotDeal.shipping.like("%무료%"))

    all_deals = query.all()

    if price_range != "all":
        filtered_deals = []
        for deal in all_deals:
            price_num = parse_price_to_number(deal.price)
            if price_range == "0-5만" and 0 < price_num <= 50000:
                filtered_deals.append(deal)
            elif price_range == "5-10만" and 50000 < price_num <= 100000:
                filtered_deals.append(deal)
            elif price_range == "10-20만" and 100000 < price_num <= 200000:
                filtered_deals.append(deal)
            elif price_range == "20만+" and price_num > 200000:
                filtered_deals.append(deal)
        all_deals = filtered_deals

    total = len(all_deals)

    if sort == "oldest":
        all_deals.sort(key=lambda x: x.created_at)
    else:
        all_deals.sort(key=lambda x: x.created_at, reverse=True)

    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    paginated_deals = all_deals[offset : offset + per_page]

    return {
        "deals": [deal.to_dict() for deal in paginated_deals],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "query": q,
    }


# 댓글 목록 API
@app.get("/api/deals/{deal_id}/comments")
async def get_comments(deal_id: int, db: Session = Depends(get_db)):
    comments = (
        db.query(Comment)
        .filter(Comment.deal_id == deal_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return {"comments": [c.to_dict() for c in comments]}


# 댓글 작성 API
@app.post("/api/deals/{deal_id}/comments")
async def create_comment(
    deal_id: int,
    content: str = Body(..., min_length=1, max_length=500),
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    user = None
    if x_access_token:
        try:
            payload = decode_token(x_access_token)
            user_id = payload.get("sub")
            if user_id:
                user = db.query(User).filter(User.id == int(user_id)).first()
        except Exception:
            pass

    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    deal = db.query(HotDeal).filter(HotDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="딜을 찾을 수 없습니다")

    comment = Comment(
        deal_id=deal_id,
        user_id=str(user.id),
        author_name=user.username,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {"comment": comment.to_dict()}


# 댓글 삭제 API
@app.delete("/api/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    user = None
    if x_access_token:
        try:
            payload = decode_token(x_access_token)
            user_id = payload.get("sub")
            if user_id:
                user = db.query(User).filter(User.id == int(user_id)).first()
        except Exception:
            pass

    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")

    if comment.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="본인 댓글만 삭제할 수 있습니다")

    db.delete(comment)
    db.commit()

    return {"status": "삭제 완료"}


# Telegram Bot 설정 API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


@app.get("/api/telegram/verify")
async def verify_telegram(token: str = Query(...)):
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=500, detail="Telegram Bot이 설정되지 않았습니다"
        )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return {
                        "status": "ok",
                        "bot_name": data["result"]["username"],
                    }
        except Exception:
            pass
    raise HTTPException(status_code=400, detail="Telegram Bot 연결 실패")


@app.post("/api/telegram/register")
async def register_telegram(
    chat_id: str = Body(...),
    categories: List[str] = Body(default=[]),
    keywords: List[str] = Body(default=[]),
    db: Session = Depends(get_db),
):
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=500, detail="Telegram Bot이 설정되지 않았습니다"
        )

    existing = db.query(TelegramUser).filter(TelegramUser.chat_id == chat_id).first()
    if existing:
        existing.categories = categories
        existing.keywords = keywords
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return {"status": "updated", "user": existing.to_dict()}

    telegram_user = TelegramUser(
        chat_id=chat_id,
        categories=categories,
        keywords=keywords,
    )
    db.add(telegram_user)
    db.commit()
    db.refresh(telegram_user)

    return {"status": "registered", "user": telegram_user.to_dict()}


@app.get("/api/telegram/status")
async def get_telegram_status(
    chat_id: str = Query(...),
    db: Session = Depends(get_db),
):
    user = db.query(TelegramUser).filter(TelegramUser.chat_id == chat_id).first()
    if not user:
        return {"is_registered": False}
    return {
        "is_registered": True,
        "is_active": user.is_active,
        "categories": user.categories,
        "keywords": user.keywords,
    }


async def send_telegram_notification(deal: dict):
    """새 딜 등록 시 Telegram 알림 발송"""
    if not TELEGRAM_BOT_TOKEN:
        return

    db = SessionLocal()
    try:
        telegram_users = (
            db.query(TelegramUser).filter(TelegramUser.is_active == True).all()
        )

        deal_category = deal.get("category", "")
        deal_title = deal.get("title", "")

        for user in telegram_users:
            should_send = False

            if user.categories and deal_category in (user.categories or []):
                should_send = True

            if user.keywords:
                for keyword in user.keywords or []:
                    if keyword.lower() in deal_title.lower():
                        should_send = True
                        break

            if not should_send:
                continue

            message = (
                f"🔥 [{deal_category}]\n"
                f"{deal_title}\n"
                f"💰 {deal.get('price', '가격 없음')} | {deal.get('shipping', '배송정보없음')}\n"
                f"📍 {deal.get('source', '출처')}\n"
                f"🔗 {deal.get('link', '')}"
            )

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": user.chat_id, "text": message},
                        timeout=10.0,
                    )
            except Exception as e:
                logger.warning(f"Telegram 메시지 발송 실패: {e}")
    finally:
        db.close()


# 수동 크롤링 API (테스트용)
@app.post("/api/crawl-now")
@limiter.limit("2/minute")
async def manual_crawl(
    request: Request,
    secret: str = "",
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)
    logger.info("수동 크롤링 요청")
    await crawl_and_save_to_db()
    return {"status": "크롤링 완료"}


# 이미지 프록시
@app.get("/image-proxy")
async def image_proxy(url: str, source: str = "뽐뿌"):
    if not is_allowed_image_url(url, source):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다")

    referer_map = {
        "뽐뿌": "https://www.ppomppu.co.kr/",
        "루리웹": "https://bbs.ruliweb.com/",
        "Zod": "https://zod.kr/",
        "어미새": "https://eomisae.co.kr/",
        "퀘이사존": "https://quasarzone.com/",
    }
    headers = {
        "Referer": referer_map.get(source, "https://www.google.com/"),
        "User-Agent": "Mozilla/5.0",
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url, headers=headers, timeout=10.0, follow_redirects=False
            )
            response.raise_for_status()
            media_type = response.headers.get("content-type", "image/jpeg")
            if not media_type.startswith("image/"):
                raise HTTPException(status_code=415, detail="이미지 응답만 허용됩니다")
            return Response(content=response.content, media_type=media_type)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"이미지 프록시 오류: {e}")
            return Response(status_code=404)


# 네이버 로그인 시작
@app.get("/api/auth/naver/login")
async def naver_login():
    """네이버 로그인 페이지로 리다이렉트"""
    state = secrets.token_urlsafe(16)

    naver_auth_url = (
        f"https://nid.naver.com/oauth2.0/authorize"
        f"?response_type=code"
        f"&client_id={NAVER_CLIENT_ID}"
        f"&redirect_uri={NAVER_CALLBACK_URL}"
        f"&state={state}"
    )

    response = JSONResponse({"url": naver_auth_url})
    response.set_cookie(
        key=NAVER_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        max_age=600,
    )
    return response


# 네이버 로그인 콜백
@app.get("/api/auth/naver/callback")
async def naver_callback(
    request: Request, code: str, state: str, db: Session = Depends(get_db)
):
    """네이버 로그인 콜백 처리"""
    saved_state = request.cookies.get(NAVER_STATE_COOKIE)
    if not saved_state or not secrets.compare_digest(state, saved_state):
        raise HTTPException(status_code=400, detail="잘못된 로그인 요청입니다")

    # 1. 액세스 토큰 발급
    token_url = "https://nid.naver.com/oauth2.0/token"
    token_params = {
        "grant_type": "authorization_code",
        "client_id": NAVER_CLIENT_ID,
        "client_secret": NAVER_CLIENT_SECRET,
        "code": code,
        "state": state,
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
        user = (
            db.query(User)
            .filter(User.provider == "naver", User.provider_id == provider_id)
            .first()
        )

        if not user:
            # 신규 사용자 생성
            user = User(
                username=f"naver_{provider_id[:10]}",
                email=email,
                provider="naver",
                provider_id=provider_id,
                profile_image=profile_image,
                hashed_password="",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # 4. JWT 토큰 생성
        jwt_token = create_access_token(data={"sub": user.id})

        # 5. 프론트엔드로 리다이렉트 (토큰 전달)
        response = RedirectResponse(url=f"{BASE_URL}/")
        response.delete_cookie(NAVER_STATE_COOKIE, samesite="lax")
        response.set_cookie(
            key=ACCESS_TOKEN_COOKIE,
            value=jwt_token,
            httponly=True,
            secure=IS_PRODUCTION,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
        )
        return response


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(ACCESS_TOKEN_COOKIE, samesite="lax")
    return response


# --- [디버깅용] 사용 가능한 Gemini 모델 리스트 확인 ---
@app.get("/api/debug/models")
async def list_available_models(
    secret: str = "",
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)
    if not GOOGLE_API_KEY:
        return {"error": "API Key 없음"}

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        models = []
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                models.append(m.name)
        return {"available_models": models}
    except Exception as e:
        logger.error(f"모델 목록 조회 오류: {e}")
        return {"error": "모델 목록 조회 실패"}


# AI 검색 API
# --- AI 검색 API (Gemini) ---
@app.get("/api/search/ai")
@limiter.limit("10/minute")
async def search_ai(request: Request, query: str, db: Session = Depends(get_db)):
    """
    [RAG 고도화 2단계] 쿼리 확장 (Query Expansion) + 하이브리드 검색 (동기식 수정)
    """
    if not query:
        return {"answer": "검색어를 입력해주세요."}

    if not GOOGLE_API_KEY:
        return {"answer": "서버에 Google API 키가 설정되지 않았습니다."}

    try:
        # --- [Step 0] AI 모델 준비 ---
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=GOOGLE_API_KEY,
            transport="rest",
        )

        # --- [Step 1] 쿼리 확장 (Query Expansion) ---
        expansion_prompt = ChatPromptTemplate.from_template(
            """사용자가 쇼핑몰에서 '{question}'(이)라고 검색했어.
            이 의도를 만족시킬 수 있는 구체적인 상품 카테고리나 키워드 5개를 한국어로 나열해줘.
            
            규칙:
            1. 쉼표(,)로만 구분해.
            2. 설명 없이 단어만 출력해.
            3. 예시: 입력 '컴퓨터' -> 출력 '노트북,데스크탑,모니터,마우스,키보드'
            """
        )

        expansion_chain = expansion_prompt | llm | StrOutputParser()

        # [수정] await 삭제 및 invoke 사용 (에러 해결 핵심)
        expanded_keywords_str = expansion_chain.invoke({"question": query})

        # 콤마로 분리하고 공백 제거
        keywords = [k.strip() for k in expanded_keywords_str.split(",")]
        keywords.insert(0, query)
        keywords = list(set(keywords))
        logger.info(f"🔍 쿼리 확장 결과: {query} -> {keywords}")

        # --- [Step 2] 벡터 검색 ---
        vector_docs = []
        vectorstore = get_vectorstore()
        if vectorstore:
            retriever = vectorstore.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={"score_threshold": 0.35, "k": 5},
            )
            try:
                vector_docs = retriever.invoke(query)
            except Exception:
                vector_docs = []

        # --- [Step 3] 키워드 검색 ---
        keyword_deals = []
        if keywords:
            conditions = [
                HotDeal.title.like(f"%{word}%") for word in keywords if len(word) > 1
            ]
            if conditions:
                sql_query = db.query(HotDeal).filter(or_(*conditions))
                keyword_deals = (
                    sql_query.order_by(desc(HotDeal.created_at)).limit(10).all()
                )

        # --- [Step 4] 결과 병합 ---
        combined_results = {}

        # 4-1. 벡터 결과
        for doc in vector_docs:
            link = doc.metadata.get("link")
            if link:
                combined_results[link] = {
                    # (중요) 끝에 URL을 명시적
                    "content": f"{doc.page_content} (링크: {link})",
                    "link": link,
                    "title": doc.page_content.split(" - ")[0],
                }

        # 4-2. 키워드 결과
        for deal in keyword_deals:
            if deal.link not in combined_results:
                combined_results[deal.link] = {
                    # (중요) 끝에 URL을 명시
                    "content": f"[{deal.source}] {deal.title} - 가격: {deal.price} (링크: {deal.link})",
                    "link": deal.link,
                    "title": f"[{deal.source}] {deal.title}",
                }

        final_docs_content = [item["content"] for item in combined_results.values()]

        if not final_docs_content:
            return {
                "answer": f"집사야, '{query}'랑 관련된 핫딜(예: {', '.join(keywords[:3])} 등)을 찾아봤는데 하나도 없다냥! 😿",
                "sources": [],
            }

        # --- [Step 5] 답변 생성 ---
        template = """너는 핫딜 정보를 분석해주는 똑똑한 고양이 '딜냥이'야.
        사용자가 '{question}'을(를) 찾고 있어.
        
        [검색된 핫딜 목록]
        {context}
        
        답변 가이드라인:
        1. 사용자의 의도에 가장 적합한 **꿀딜 1~3개만 콕 집어서 추천**해줘.
        2. **(중요) 상품명을 말할 때는 반드시 링크를 걸어줘.** 형식: `[상품명](링크URL)` 
           예시: `[농심 신라면 20봉](http://...)
        3. 추천 이유는 짧게 덧붙여줘.
        4. 엉뚱한 물건(사용자 질문과 관련 없는 것)은 절대 추천하지 마.
        5. 말투는 친절한 고양이 말투('~이다냥', '~했다냥')를 써줘.
        """
        prompt = ChatPromptTemplate.from_template(template)

        chain = (
            {
                "context": lambda x: "\n".join(final_docs_content),
                "question": RunnablePassthrough(),
                "keywords": lambda x: ", ".join(keywords),
            }
            | prompt
            | llm
            | StrOutputParser()
        )

        # [수정] 여기도 invoke 사용
        response = chain.invoke(query)

        sources = [
            {"title": item["title"], "link": item["link"]}
            for item in list(combined_results.values())[:10]
        ]

        return {"answer": response, "sources": sources}

    except Exception as e:
        logger.error(f"AI 검색 오류: {e}")
        return {
            "answer": "죄송해요, 지금 검색이 꼬여서 답변을 못했어요 😿 잠시 후 다시 시도해줘!"
        }


# 현재 유저 정보 조회
@app.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user_required)):
    """현재 로그인한 유저 정보"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "provider": current_user.provider,
        "profile_image": current_user.profile_image,
        "created_at": current_user.created_at.strftime("%Y-%m-%d"),
    }


# --- [관리자용] DB 강제 동기화 API ---
@app.get("/api/admin/sync-rag")
async def sync_rag_manually(
    secret: str = "",
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
):
    """기존 DB의 데이터를 벡터 DB로 강제 이식"""
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)
    if not GOOGLE_API_KEY:
        return {"status": "error", "message": "Google API Key 없음"}

    try:
        # 1. 모든 핫딜 가져오기
        all_deals = db.query(HotDeal).all()
        if not all_deals:
            return {"status": "empty", "message": "DB에 데이터가 없습니다."}

        # 2. 벡터 문서로 변환
        documents = []
        for deal in all_deals:
            documents.append(
                make_rag_document(
                    {
                        "link": deal.link,
                        "source": deal.source,
                        "title": deal.title,
                        "price": deal.price,
                    }
                )
            )

        # 3. 벡터 DB에 저장
        vectorstore = get_vectorstore()
        if vectorstore:
            vectorstore.reset_collection()
            upsert_rag_documents(vectorstore, documents)

        return {
            "status": "success",
            "message": f"총 {len(documents)}개의 핫딜을 AI에게 학습시켰습니다!",
        }

    except Exception as e:
        logger.error(f"동기화 실패: {e}")
        return {"status": "error", "message": str(e)}


# 정적 파일 제공
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")


# main.js 직접 서빙 추가
@app.get("/main.js")
async def serve_main_js():
    file_path = os.path.join(templates_dir, "main.js")
    return FileResponse(file_path, media_type="application/javascript")


@app.get("/", response_class=FileResponse)
async def read_root():
    return os.path.join(templates_dir, "index.html")


# 헬스체크 엔드포인트
@app.get("/health")
async def health_check():
    """기본 헬스체크"""
    return {"status": "ok", "service": "shopcrawl"}


@app.get("/health/db")
async def health_db(db: Session = Depends(get_db)):
    """DB 연결 확인"""
    try:
        db.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"DB 헬스체크 실패: {e}")
        return {"status": "error", "database": "disconnected", "error": str(e)}


@app.get("/health/vectorstore")
async def health_vectorstore():
    """ChromaDB 연결 확인"""
    try:
        if not GOOGLE_API_KEY:
            return {
                "status": "warning",
                "vectorstore": "not_configured",
                "reason": "Google API Key 없음",
            }

        vectorstore = get_vectorstore()
        if vectorstore:
            collection = vectorstore._collection
            count = collection.count()
            return {"status": "ok", "vectorstore": "connected", "document_count": count}
        else:
            return {"status": "error", "vectorstore": "not_initialized"}
    except Exception as e:
        logger.error(f"VectorStore 헬스체크 실패: {e}")
        return {"status": "error", "vectorstore": "error", "error": str(e)}


# app.mount("/", StaticFiles(directory=templates_dir, html=True), name="static")

# 새 코드 (Railway에서는 사용 안 함)
if __name__ == "__main__":
    import sys

    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 로컬 서버 시작: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
