from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz
import os

Base = declarative_base()
KST = pytz.timezone('Asia/Seoul')

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, index=True)
    hashed_password = Column(String, default="")  # 소셜 로그인은 빈값
    
    # 소셜 로그인 필드 추가
    provider = Column(String, default="local", index=True)  # "local", "naver", "kakao"
    provider_id = Column(String, index=True)  # 네이버 고유 ID
    profile_image = Column(String)  # 프로필 이미지 URL
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None))

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
    created_at = Column(DateTime, default=lambda: datetime.now(KST).replace(tzinfo=None), index=True)
    
    def to_dict(self):
        return {
            "title": self.title,
            "source": self.source,
            "author": self.author,
            "price": self.price,
            "shipping": self.shipping,
            "link": self.link,
            "thumbnail": self.thumbnail,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

# 데이터베이스 설정
# current_dir = os.path.dirname(os.path.abspath(__file__))
# db_path = os.path.join(current_dir, "hotdeals.db")
db_path = "/data/hotdeals.db"  # <- 이 경로로 변경
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

print(f"데이터베이스 생성됨: {db_path}")
