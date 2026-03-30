import asyncio
import os
import shutil
import logging
from datetime import datetime, timedelta
from typing import List
import pytz

from models import HotDeal, SessionLocal, PriceHistory
from core.helpers import parse_price_to_number

KST = pytz.timezone("Asia/Seoul")
logger = logging.getLogger(__name__)

_hotdeals_cache = {}
CACHE_TTL = 30


def backup_database():
    """DB 백업 (프로덕션 환경에서만)"""
    IS_PRODUCTION = os.getenv("APP_ENV") == "production"
    if not IS_PRODUCTION:
        logger.info("⏭️ 로컬 환경: DB 백업 스킵")
        return

    db_path = "/data/hotdeals.db"
    backup_dir = "/data/backups"
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/hotdeals_backup_{timestamp}.db"

    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"✅ DB 백업 완료: {backup_path}")

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

    CHROMA_DB_DIR = "/data/chroma_db"
    chroma_backup_path = f"{backup_dir}/chroma_backup_{timestamp}"
    try:
        if os.path.exists(CHROMA_DB_DIR):
            if os.path.exists(chroma_backup_path):
                shutil.rmtree(chroma_backup_path)
            shutil.copytree(CHROMA_DB_DIR, chroma_backup_path)
            logger.info(f"✅ ChromaDB 백업 완료: {chroma_backup_path}")

            chroma_backups = sorted(
                [f for f in os.listdir(backup_dir) if f.startswith("chroma_backup_")],
                reverse=True,
            )
            for old_backup in chroma_backups[7:]:
                old_path = os.path.join(backup_dir, old_backup)
                shutil.rmtree(old_path)
                logger.info(f"🗑️ 오래된 ChromaDB 백업 삭제: {old_backup}")
    except Exception as e:
        logger.error(f"❌ ChromaDB 백업 실패: {e}")


def cleanup_old_deals():
    """30일 이상된 핫딜 및 ChromaDB orphan vectors 정리"""
    import chromadb
    from chromadb.config import Settings
    from core.helpers import make_rag_id

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

    IS_PRODUCTION = os.getenv("APP_ENV") == "production"
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if deleted_links and GOOGLE_API_KEY and IS_PRODUCTION:
        try:
            from services.rag import get_vectorstore

            vectorstore = get_vectorstore()
            if vectorstore:
                rag_ids_to_delete = [make_rag_id(link) for link in deleted_links]
                vectorstore.delete(ids=rag_ids_to_delete)
                logger.info(
                    f"🧠 ChromaDB 정리: {len(rag_ids_to_delete)}개 orphan vectors 삭제"
                )
        except Exception as e:
            logger.error(f"❌ ChromaDB 정리 오류: {e}")


async def with_retry(coro_func, max_retries: int = 3, base_delay: float = 1.0):
    """재시도 로직 헬퍼"""
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await coro_func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"{coro_func.__name__} 실패 (시도 {attempt + 1}/{max_retries}), {delay}s 후 재시도: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"{coro_func.__name__} 최종 실패: {e}")
    return []


def make_rag_document(deal: dict):
    from langchain_core.documents import Document
    from core.helpers import make_rag_id as _make_rag_id

    return Document(
        page_content=f"[{deal['source']}] {deal['title']} - 가격: {deal['price']}",
        metadata={
            "link": deal["link"],
            "source": deal["source"],
            "price": deal["price"],
            "rag_id": _make_rag_id(deal["link"]),
        },
    )


async def crawl_and_save_to_db():
    """전체 크롤링 및 DB 저장"""
    from services.scraper import (
        scrape_ppomppu,
        scrape_quasarzone,
        scrape_ruliweb,
        scrape_eomisae,
        scrape_zod,
    )
    from services.rag import upsert_rag_documents, get_vectorstore

    logger.info(
        f"=== 백그라운드 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
    )

    all_deals = []

    logger.info("--- 크롤러 5개 병렬 시작 ---")
    tasks = [
        with_retry(scrape_ppomppu, max_retries=3, base_delay=2.0),
        with_retry(scrape_quasarzone, max_retries=3, base_delay=2.0),
        with_retry(scrape_ruliweb, max_retries=3, base_delay=2.0),
        with_retry(scrape_eomisae, max_retries=3, base_delay=2.0),
        with_retry(scrape_zod, max_retries=3, base_delay=2.0),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"크롤링 오류: {result}")
        else:
            all_deals.extend(result)
    logger.info("--- 크롤러 5개 완료 ---")

    if not all_deals:
        return

    db = SessionLocal()
    new_count = 0
    duplicate_count = 0

    deals_for_rag = []

    try:
        for deal in all_deals:
            try:
                existing = (
                    db.query(HotDeal).filter(HotDeal.link == deal["link"]).first()
                )

                if existing:
                    price_changed = existing.price != deal["price"]
                    changed = (
                        existing.title != deal["title"]
                        or price_changed
                        or existing.shipping != deal["shipping"]
                        or existing.thumbnail != deal["thumbnail"]
                        or existing.category != deal.get("category", "기타")
                    )
                    existing.title = deal["title"]
                    existing.price = deal["price"]
                    existing.price_value = parse_price_to_number(deal["price"])
                    existing.shipping = deal["shipping"]
                    existing.thumbnail = deal["thumbnail"]
                    existing.category = deal.get("category", "기타")
                    duplicate_count += 1

                    if price_changed:
                        price_history = PriceHistory(
                            deal_id=existing.id,
                            price=deal["price"],
                            price_value=parse_price_to_number(deal["price"]),
                            recorded_at=datetime.now(KST).replace(tzinfo=None),
                        )
                        db.add(price_history)
                        logger.info(
                            f"💰 가격 변동 기록: {existing.title[:30]}... {existing.price} -> {deal['price']}"
                        )

                    if changed:
                        deals_for_rag.append(make_rag_document(deal))
                else:
                    deal["price_value"] = parse_price_to_number(deal["price"])
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

        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
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
