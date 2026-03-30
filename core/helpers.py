import os
import re
import hashlib
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")

ALLOWED_IMAGE_HOST_SUFFIXES = {
    "뽐뿌": {"ppomppu.co.kr"},
    "루리웹": {"ruliweb.com"},
    "Zod": {"zod.kr"},
    "어미새": {"eomisae.co.kr"},
    "퀘이사존": {"quasarzone.com"},
}


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


def clean_deal_title(title: str) -> str:
    """핫딜 제목에서 의미없는 텍스트 제거"""
    if not title:
        return ""

    cleaned = title

    patterns_to_remove = [
        r"\[.*?\]",
        r"\s*\([^)]*\)",
        r"\s*/\s*무료배송",
        r"\s*/\s*무배",
        r"\s*/\s*무료\s*",
        r"\s*/\s*\d+원?",
        r"\s*\|\s*.*$",
        r"\s*&\s*.*$",
        r"\s*=\s*.*$",
        r"\d{1,3}(?:,\d{3})*원\s*$",
        r"\d+만\s*원\s*$",
        r"^\s*\d+\s*$",
        r"^\s*-\s*",
    ]

    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^[\s\-–—\.]+|[\s\-–—\.]+$", "", cleaned)

    return cleaned.strip()


def make_rag_id(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def is_valid_admin_secret(candidate: str, admin_secret: str) -> bool:
    return (
        bool(admin_secret)
        and bool(candidate)
        and secrets.compare_digest(candidate, admin_secret)
    )


def is_allowed_image_url(raw_url: str, source: str) -> bool:
    from urllib.parse import urlparse
    import secrets

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


import secrets
