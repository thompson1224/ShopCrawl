from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from models import User, SessionLocal
import os

# .env 파일 로드 (로컬 개발용, 배포 환경에서는 무시됨)
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# SECRET_KEY 가져오기 (환경변수에서 직접)
SECRET_KEY = os.getenv("SECRET_KEY")

# Railway 환경에서는 에러 메시지만 출력하고 계속 진행
if not SECRET_KEY:
    print("⚠️ WARNING: SECRET_KEY가 설정되지 않았습니다. 기본값을 사용합니다.")
    print("⚠️ 프로덕션 환경에서는 반드시 SECRET_KEY 환경변수를 설정하세요!")
    SECRET_KEY = "temporary-secret-key-please-change-in-production-" + os.urandom(16).hex()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7일

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """JWT 토큰 생성"""
    to_encode = data.copy()
    
    # subject를 문자열로 변환
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """현재 로그인한 유저 정보 가져오기"""
    if not credentials:
        return None
    
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            return None
        
        user_id = int(user_id_str)
        
    except (JWTError, ValueError) as e:
        print(f"JWT 에러: {e}")
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user

def get_current_user_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """로그인 필수"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_current_user(credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 정보입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
