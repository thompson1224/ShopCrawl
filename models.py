from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Index,
    Enum,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import pytz
import os
from enum import Enum as PyEnum

Base = declarative_base()
KST = pytz.timezone("Asia/Seoul")


class Category(PyEnum):
    HOME_APPLIANCES = "가전/디지털"
    FASHION = "신세계/아웃렛"
    BEAUTY = "뷰티/화장품"
    FOOD = "식품/건강"
    FURNITURE = "가구/인테리어"
    HOBBY = "게임/취미"
    OTHER = "기타"


CATEGORY_KEYWORDS = {
    Category.HOME_APPLIANCES: [
        "노트북",
        "태블릿",
        "스마트폰",
        "모니터",
        "키보드",
        "마우스",
        "이어폰",
        "충전기",
        "에어팟",
        "와이파이",
        "SSD",
        "메모리",
        "HDD",
        "웹캠",
        "카메라",
        "프린터",
        "라즈베리파이",
        "아이폰",
        "갤럭시",
        "애플워치",
        "갤워치",
        "헤드폰",
        "스피커",
        "TV",
        "냉장고",
        "세탁기",
        "에어컨",
        "청소기",
        "전자레인지",
        "오븐",
        "믹서기",
        "커피머신",
        "LG",
        "삼성",
        "LG트롬",
        "드럼세탁기",
        "냉온숨소",
        "공기청정기",
        "加湿器",
        "，空气清净기",
    ],
    Category.FASHION: [
        "신발",
        "가방",
        "지갑",
        "벨트",
        "가죽",
        "명품",
        "나이키",
        "아디다스",
        "슈콤",
        "구두",
        "로퍼",
        "스니커즈",
        "샌들",
        "슬리퍼",
        "부츠",
        "运动鞋",
        "가이걸",
        "미스키",
        "멀버리",
        "보세",
        "시골쌀",
        "패션",
        "옷",
        "의류",
        "티셔츠",
        "셔츠",
        "바지",
        "치마",
        "원피스",
        "재킷",
        "코트",
        "점퍼",
        "니트",
        "후드",
        "양말",
        "모자",
        "스카프",
        "넥타이",
        "쥬얼리",
        "액세서리",
        "루이비통",
        "구찌",
        "샤넬",
        "에르메스",
        "프라다",
        "발망",
        "버버리",
    ],
    Category.BEAUTY: [
        "화장품",
        "스킨케어",
        "메이크업",
        "향수",
        "클렌징",
        "선크림",
        "바디",
        "헤어",
        "미용",
        "에뛰드",
        "라ashes",
        "미쟝",
        "려",
        "아모르파시",
        "더후",
        "쿠incare",
        "톤크림",
        "마스카라",
        "아이섀도우",
        "립스틱",
        "립밤",
        "핸드크림",
        "바디로션",
        "바디워시",
        "샴푸",
        "컨디셔너",
        "헤어에센스",
        "드라이기",
        "고데기",
    ],
    Category.FOOD: [
        "음식",
        "식품",
        "커피",
        "과일",
        "건강",
        "비타민",
        "유산균",
        "다이어트",
        "스포츠",
        "요가",
        "운동",
        "쥬스",
        "음료",
        "차",
        "꿀",
        "떡",
        "한정",
        "한식",
        "중식",
        "일식",
        "양식",
        "패스트푸드",
        "도시락",
        "반찬",
        "김치",
        "젓갈",
        "장아찌",
        "묵",
        "두부",
        "달걀",
        "고기",
        "소고기",
        "돼지고기",
        "닭고기",
        "양고기",
        "해산물",
        "生선",
        "건어물",
        "바다",
        "山谷",
    ],
    Category.FURNITURE: [
        "가구",
        "침구",
        "쿠션",
        "조명",
        "인테리어",
        "커튼",
        "러그",
        "수납",
        "整理",
        "책상",
        "의자",
        "책장",
        "서랍",
        "행거",
        "옷장",
        "화장대",
        "침대",
        "매트리스",
        "토퍼",
        "이불",
        "pillow",
        "쿠션",
        "방석",
        "카페트",
        "러그",
        "카펫",
        "두께",
        "학습 desk",
        "컴퓨터 desk",
        "standing desk",
        "조명",
        "스탠드",
        "천장등",
        "벽등",
        "LED",
        "무드등",
        "인테리어소품",
    ],
    Category.HOBBY: [
        "게임",
        "보드게임",
        "장난감",
        "피규어",
        "굿즈",
        "만화",
        "애니",
        "書籍",
        "음악",
        "악기",
        "캠핑",
        "등산",
        "자전거",
        "피씨방",
        "노트",
        "문구",
        "플래너",
        "다이어리",
        "스티커",
        "마스킹테이프",
        "키링",
        "인형",
        " plush",
        "레고",
        "반다이",
        "마리오",
        "짱구",
        "고염전",
        "테니스",
        "배드민턴",
        "탁구",
        "볼링",
        "스쿠버",
        "서핑",
        "스키",
        "보드",
        "당구",
        "포켓볼",
    ],
}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, index=True)
    hashed_password = Column(String, default="")

    provider = Column(String, default="local", index=True)
    provider_id = Column(String, index=True)
    profile_image = Column(String)

    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None)
    )

    comments = relationship(
        "Comment", back_populates="user", cascade="all, delete-orphan"
    )


class HotDeal(Base):
    __tablename__ = "hotdeals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    source = Column(String, index=True)
    author = Column(String)
    price = Column(String)
    shipping = Column(String)
    link = Column(String, unique=True, index=True)
    thumbnail = Column(String)
    category = Column(String, default="기타")
    created_at = Column(
        DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None), index=True
    )

    comments = relationship(
        "Comment", back_populates="deal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_hotdeals_source_created", "source", "created_at"),
        Index("ix_hotdeals_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "author": self.author,
            "price": self.price,
            "shipping": self.shipping,
            "link": self.link,
            "thumbnail": self.thumbnail,
            "category": self.category,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(
        Integer, ForeignKey("hotdeals.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String(100))
    author_name = Column(String(100))
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None)
    )

    deal = relationship("HotDeal", back_populates="comments")
    user = relationship("User", back_populates="comments")

    def to_dict(self):
        return {
            "id": self.id,
            "deal_id": self.deal_id,
            "user_id": self.user_id,
            "author_name": self.author_name,
            "content": self.content,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String(100), unique=True, nullable=False)
    username = Column(String(100))
    categories = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "username": self.username,
            "categories": self.categories,
            "keywords": self.keywords,
            "is_active": self.is_active,
        }


class RuliwebThumbnail(Base):
    __tablename__ = "ruliweb_thumbnails"

    link = Column(String, primary_key=True)
    thumbnail_url = Column(String)
    fetched_at = Column(
        DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None)
    )


def classify_category(title: str) -> str:
    """제목 키워드 매칭으로 카테고리 분류"""
    title_lower = title.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in title_lower:
                return category.value

    return Category.OTHER.value


def create_fts_table(engine):
    """FTS5 가상 테이블 생성 (검색용)"""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS deals_fts USING fts5(
                title,
                content='hotdeals',
                content_rowid='id'
            )
        """)
        )
        conn.commit()


if os.getenv("APP_ENV") == "production":
    db_path = "/data/hotdeals.db"
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, "hotdeals.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)
create_fts_table(engine)
