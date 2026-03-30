import asyncio
import httpx
import re
import logging
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
from sqlalchemy.orm import Session

from core.helpers import clean_deal_title, parse_price_to_number, is_allowed_image_url
from models import HotDeal, RuliwebThumbnail, SessionLocal, classify_category

KST = pytz.timezone("Asia/Seoul")
logger = logging.getLogger(__name__)


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
        except Exception as e:
            logger.warning(f"뽐뿌 항목 파싱 오류: {e}")
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

                    price = parse_price_to_number(full_title)
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
                except Exception as e:
                    logger.warning(f"루리웹 항목 파싱 오류: {e}")
                    continue

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
                    except Exception as e:
                        logger.warning(f"루리웹 og:image fetch 실패: {url} - {e}")
                        return ""

            if links_to_fetch:
                unique_links_to_fetch = list(dict.fromkeys(links_to_fetch))
                thumbnails = await asyncio.gather(
                    *[fetch_og_image(link) for link in unique_links_to_fetch]
                )
                fetched_thumbnail_map = {
                    link: thumb
                    for link, thumb in zip(unique_links_to_fetch, thumbnails)
                    if thumb
                }

                for deal in deal_list:
                    thumb = fetched_thumbnail_map.get(deal["link"])
                    if thumb:
                        deal["thumbnail"] = thumb

                if fetched_thumbnail_map:
                    db = SessionLocal()
                    try:
                        existing_records = (
                            db.query(RuliwebThumbnail)
                            .filter(
                                RuliwebThumbnail.link.in_(
                                    list(fetched_thumbnail_map.keys())
                                )
                            )
                            .all()
                        )
                        existing_map = {
                            record.link: record for record in existing_records
                        }

                        for link, thumb in fetched_thumbnail_map.items():
                            existing = existing_map.get(link)
                            if existing:
                                existing.thumbnail_url = thumb
                                existing.fetched_at = datetime.now(KST).replace(
                                    tzinfo=None
                                )
                            else:
                                db.add(
                                    RuliwebThumbnail(
                                        link=link,
                                        thumbnail_url=thumb,
                                        fetched_at=datetime.now(KST).replace(
                                            tzinfo=None
                                        ),
                                    )
                                )
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
            except Exception as e:
                logger.warning(f"Zod 항목 파싱 오류: {e}")
                continue

    except Exception as e:
        logger.error(f"Zod 크롤링 오류: {e}")

    logger.info(f"Zod 크롤링 완료: {len(deal_list)}개")
    return deal_list


async def scrape_quasarzone():
    logger.info("퀘이사존 크롤링 시작")
    deal_list = []

    try:
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

        posts = soup.find_all("div", class_="market-info-list")
        logger.info(f"퀘이사존: {len(posts)}개 게시글 발견")

        for idx, item in enumerate(posts[:20]):
            try:
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

                author = "작성자"
                nick_wrap = cont.find("span", class_="nick")
                if nick_wrap:
                    author = nick_wrap.get_text(strip=True)

                price = "가격 정보 없음"
                price_el = cont.select_one("span.text-orange")
                if price_el:
                    raw = price_el.get_text(strip=True)
                    price_match = re.search(r"[\d,]+", raw)
                    if price_match:
                        price = price_match.group(0) + "원"
                else:
                    price_match = re.search(r"(\d{1,3}(?:,\d{3})*원)", title)
                    if price_match:
                        price = price_match.group(1)

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

                price = parse_price_to_number(title)
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
