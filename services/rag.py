import os
import logging
from typing import Optional
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

logger = logging.getLogger(__name__)

CHROMA_DB_DIR = (
    "/data/chroma_db" if os.getenv("APP_ENV") == "production" else "./chroma_db"
)


def get_vectorstore() -> Optional[Chroma]:
    """벡터 DB(기억장치) 가져오기"""
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        return None

    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004", google_api_key=GOOGLE_API_KEY
        )

        vectorstore = Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=embeddings,
            collection_name="hotdeals",
        )
        return vectorstore
    except Exception as e:
        logger.error(f"VectorStore 초기화 실패: {e}")
        return None


def upsert_rag_documents(vectorstore: Chroma, documents: list) -> None:
    """RAG 문서 추가/갱신"""
    if not documents:
        return

    try:
        ids = [doc.metadata["rag_id"] for doc in documents]
        vectorstore.delete(ids=ids)
        vectorstore.add_documents(documents, ids=ids)
    except Exception as e:
        logger.error(f"RAG 문서 저장 실패: {e}")
        raise
