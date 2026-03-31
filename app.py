import os
import asyncio
import logging
import json
import httpx
import time
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Depends, Header, Query, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_current_user_required,
    get_db,
    decode_token,
)
from models import User, HotDeal, Comment, TelegramUser, Bookmark, PriceHistory
from core.helpers import (
    parse_price_to_number,
    clean_deal_title,
    is_allowed_image_url,
    is_valid_admin_secret,
    KST,
)
from services.database import (
    crawl_and_save_to_db,
    backup_database,
    cleanup_old_deals,
    _hotdeals_cache,
    CACHE_TTL,
)
from services.rag import get_vectorstore, upsert_rag_documents

try:
    from dotenv import load_dotenv

    load_dotenv()
except:
    pass

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IS_PRODUCTION = os.getenv("APP_ENV") == "production"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
PORT = int(os.getenv("PORT", 8000))

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

try:
    app.mount("/static", StaticFiles(directory="templates"), name="static")
except:
    pass

templates = Jinja2Templates(directory="templates")


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


def require_admin_access(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
) -> None:
    provided_secret = x_admin_secret or secret
    if not is_valid_admin_secret(provided_secret, ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="관리자 인증이 필요합니다")


scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 서버 시작: 백그라운드 스케줄러 활성화")

    scheduler.add_job(
        crawl_and_save_to_db,
        "date",
        run_date=datetime.now(KST) + timedelta(seconds=5),
        id="first_crawl",
        timezone=KST,
    )

    scheduler.add_job(
        crawl_and_save_to_db, "interval", minutes=5, id="crawl_job", timezone=KST
    )

    scheduler.add_job(
        backup_database, "cron", hour=3, minute=0, id="backup_job", timezone=KST
    )

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

    if price_range != "all":
        if price_range == "0-5만":
            query = query.filter(
                and_(HotDeal.price_value > 0, HotDeal.price_value <= 50000)
            )
        elif price_range == "5-10만":
            query = query.filter(
                and_(HotDeal.price_value > 50000, HotDeal.price_value <= 100000)
            )
        elif price_range == "10-20만":
            query = query.filter(
                and_(HotDeal.price_value > 100000, HotDeal.price_value <= 200000)
            )
        elif price_range == "20만+":
            query = query.filter(HotDeal.price_value > 200000)

    all_deals = query.all()
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
    query = db.query(HotDeal)

    if q:
        escaped_q = q.replace("%", r"\%").replace("_", r"\_")
        query = query.filter(HotDeal.title.like(f"%{escaped_q}%"))

    if category != "all":
        query = query.filter(HotDeal.category == category)

    if shipping_free:
        query = query.filter(HotDeal.shipping.like("%무료%"))

    if price_range != "all":
        if price_range == "0-5만":
            query = query.filter(
                and_(HotDeal.price_value > 0, HotDeal.price_value <= 50000)
            )
        elif price_range == "5-10만":
            query = query.filter(
                and_(HotDeal.price_value > 50000, HotDeal.price_value <= 100000)
            )
        elif price_range == "10-20만":
            query = query.filter(
                and_(HotDeal.price_value > 100000, HotDeal.price_value <= 200000)
            )
        elif price_range == "20만+":
            query = query.filter(HotDeal.price_value > 200000)

    all_deals = query.all()
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


@app.get("/api/deals/{deal_id}/comments")
async def get_comments(deal_id: int, db: Session = Depends(get_db)):
    comments = (
        db.query(Comment)
        .filter(Comment.deal_id == deal_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return {"comments": [c.to_dict() for c in comments]}


@app.post("/api/deals/{deal_id}/comments")
async def create_comment(
    deal_id: int,
    content: str = Body(..., min_length=1, max_length=500),
    x_access_token: Optional[str] = Header(default=None, alias="X-Access-Token"),
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


@app.delete("/api/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    x_access_token: Optional[str] = Header(default=None, alias="X-Access-Token"),
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


@app.get("/api/bookmarks")
async def get_bookmarks(
    request: Request,
    x_access_token: Optional[str] = Header(default=None, alias="X-Access-Token"),
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

    bookmarks = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == str(user.id))
        .order_by(Bookmark.created_at.desc())
        .all()
    )

    deals = []
    for bm in bookmarks:
        deal = db.query(HotDeal).filter(HotDeal.id == bm.deal_id).first()
        if deal:
            deals.append(deal.to_dict())

    return {"bookmarks": deals}


@app.post("/api/bookmarks/{deal_id}")
async def add_bookmark(
    deal_id: int,
    request: Request,
    x_access_token: Optional[str] = Header(default=None, alias="X-Access-Token"),
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

    existing = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == str(user.id), Bookmark.deal_id == deal_id)
        .first()
    )
    if existing:
        return {"status": "already_exists", "message": "이미 북마크된 딜입니다"}

    bookmark = Bookmark(
        user_id=str(user.id),
        deal_id=deal_id,
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)

    return {"status": "added", "bookmark": bookmark.to_dict()}


@app.delete("/api/bookmarks/{deal_id}")
async def remove_bookmark(
    deal_id: int,
    request: Request,
    x_access_token: Optional[str] = Header(default=None, alias="X-Access-Token"),
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

    bookmark = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == str(user.id), Bookmark.deal_id == deal_id)
        .first()
    )
    if not bookmark:
        raise HTTPException(status_code=404, detail="북마크를 찾을 수 없습니다")

    db.delete(bookmark)
    db.commit()

    return {"status": "deleted"}


@app.get("/api/deals/{deal_id}/price-history")
async def get_price_history(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(HotDeal).filter(HotDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="딜을 찾을 수 없습니다")

    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.deal_id == deal_id)
        .order_by(PriceHistory.recorded_at.desc())
        .limit(30)
        .all()
    )

    current_price = deal.price
    price_value = deal.price_value

    price_changes = []
    for h in history:
        price_changes.append(
            {
                "price": h.price,
                "price_value": h.price_value,
                "recorded_at": h.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return {
        "deal_id": deal_id,
        "current_price": current_price,
        "current_price_value": price_value,
        "history": price_changes,
    }


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

    from models import SessionLocal

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


@app.post("/api/crawl-now")
@limiter.limit("2/minute")
async def manual_crawl(
    request: Request,
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)
    logger.info("수동 크롤링 요청")
    await crawl_and_save_to_db()
    return {"status": "크롤링 완료"}


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


@app.get("/api/auth/naver/callback")
async def naver_callback(
    request: Request, code: str, state: str, db: Session = Depends(get_db)
):
    """네이버 로그인 콜백 처리"""
    saved_state = request.cookies.get(NAVER_STATE_COOKIE)
    if not saved_state or not secrets.compare_digest(state, saved_state):
        raise HTTPException(status_code=400, detail="잘못된 로그인 요청입니다")

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

        user = (
            db.query(User)
            .filter(User.provider == "naver", User.provider_id == provider_id)
            .first()
        )

        if not user:
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

        jwt_token = create_access_token(data={"sub": user.id})

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


@app.get("/api/debug/models")
async def list_available_models(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
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


@app.get("/api/search/ai")
@limiter.limit("10/minute")
async def search_ai(request: Request, query: str, db: Session = Depends(get_db)):
    if not query:
        return {"answer": "검색어를 입력해주세요."}

    if not GOOGLE_API_KEY:
        return {"answer": "서버에 Google API 키가 설정되지 않았습니다."}

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=GOOGLE_API_KEY,
            transport="rest",
        )

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
        expanded_keywords_str = expansion_chain.invoke({"question": query})

        keywords = [k.strip() for k in expanded_keywords_str.split(",")]
        keywords.insert(0, query)
        keywords = list(set(keywords))

        vectorstore = get_vectorstore()
        if not vectorstore:
            return {"answer": "벡터 DB 연결 실패"}

        from langchain_core.documents import Document
        from core.helpers import make_rag_id

        combined_query = " OR ".join(keywords)
        results = vectorstore.similarity_search(combined_query, k=10)

        context_deals = []
        for doc in results:
            link = doc.metadata.get("link", "")
            deal = db.query(HotDeal).filter(HotDeal.link == link).first()
            if deal:
                context_deals.append(deal.to_dict())

        if not context_deals:
            return {
                "answer": f"'{query}' 관련 결과를 찾지 못했습니다.",
                "deals": [],
            }

        deals_text = "\n".join(
            [
                f"- [{d['source']}] {d['title']} | {d['price']} | {d['shipping']}"
                for d in context_deals
            ]
        )

        answer_prompt = ChatPromptTemplate.from_template(
            """다음은 쇼핑 검색 '{query}'에 대한 결과입니다:
            {context}
            
            위 결과를 바탕으로 사용자에게 최적의 쇼핑 추천 답변을 한국어로 작성해주세요.
            3-5개 추천하며, 각 추천마다 간단한 이유도 포함해주세요.
            """
        )

        answer_chain = answer_prompt | llm | StrOutputParser()
        answer = answer_chain.invoke({"query": query, "context": deals_text})

        return {
            "answer": answer,
            "deals": context_deals,
            "expanded_keywords": keywords,
        }

    except Exception as e:
        logger.error(f"AI 검색 오류: {e}")
        return {"answer": f"검색 중 오류가 발생했습니다: {str(e)}"}


@app.get("/api/auth/me")
async def get_me(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, credentials, db)
    if not user:
        return {"user": None}
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "profile_image": user.profile_image,
            "provider": user.provider,
        }
    }


@app.get("/api/admin/sync-rag")
async def sync_rag(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)

    if not GOOGLE_API_KEY:
        return {"error": "Google API Key 없음"}

    try:
        from services.database import make_rag_document

        vectorstore = get_vectorstore()
        if not vectorstore:
            return {"error": "VectorStore 초기화 실패"}

        all_deals = db.query(HotDeal).all()
        documents = [make_rag_document(deal.to_dict()) for deal in all_deals]

        upsert_rag_documents(vectorstore, documents)

        return {"status": "success", "synced": len(documents)}
    except Exception as e:
        logger.error(f"RAG Sync 오류: {e}")
        return {"error": str(e)}


@app.get("/api/admin/stats")
async def admin_stats(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)

    total_deals = db.query(HotDeal).count()
    total_users = db.query(User).count()
    total_comments = db.query(Comment).count()
    total_bookmarks = db.query(Bookmark).count()
    total_telegram_users = db.query(TelegramUser).count()

    source_stats = {}
    for source in ["뽐뿌", "루리웹", "Zod", "어미새", "퀘이사존"]:
        count = db.query(HotDeal).filter(HotDeal.source == source).count()
        source_stats[source] = count

    category_stats = {}
    for category in [
        "가전/디지털",
        "신세계/아웃렛",
        "뷰티/화장품",
        "식품/건강",
        "가구/인테리어",
        "게임/취미",
        "기타",
    ]:
        count = db.query(HotDeal).filter(HotDeal.category == category).count()
        category_stats[category] = count

    return {
        "total_deals": total_deals,
        "total_users": total_users,
        "total_comments": total_comments,
        "total_bookmarks": total_bookmarks,
        "total_telegram_users": total_telegram_users,
        "source_stats": source_stats,
        "category_stats": category_stats,
    }


@app.get("/api/admin/users")
async def admin_list_users(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)

    total = db.query(User).count()
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "provider": u.provider,
                "is_active": u.is_active,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if u.created_at
                else None,
            }
            for u in users
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@app.delete("/api/admin/deals/{deal_id}")
async def admin_delete_deal(
    deal_id: int,
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)

    deal = db.query(HotDeal).filter(HotDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="딜을 찾을 수 없습니다")

    db.delete(deal)
    db.commit()

    return {"status": "deleted", "deal_id": deal_id}


@app.get("/api/admin/deals")
async def admin_list_deals(
    secret: str = "",
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    source: str = "all",
):
    require_admin_access(secret=secret, x_admin_secret=x_admin_secret)

    query = db.query(HotDeal)
    if source != "all":
        query = query.filter(HotDeal.source == source)

    total = query.count()
    deals = (
        query.order_by(HotDeal.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "deals": [d.to_dict() for d in deals],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@app.get("/main.js")
async def main_js():
    return FileResponse("templates/main.js")


@app.get("/", response_class=FileResponse)
async def read_root():
    return FileResponse("templates/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/health/db")
async def health_db(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "error", "error": str(e)}


@app.get("/health/vectorstore")
async def health_vectorstore():
    try:
        vectorstore = get_vectorstore()
        if vectorstore:
            return {"status": "ok", "vectorstore": "connected"}
        return {"status": "error", "vectorstore": "not_initialized"}
    except Exception as e:
        logger.error(f"VectorStore 헬스체크 실패: {e}")
        return {"status": "error", "vectorstore": "error", "error": str(e)}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 로컬 서버 시작: http://localhost:{port}")
    # Uvicorn reload mode requires an import string, not the app object itself.
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
