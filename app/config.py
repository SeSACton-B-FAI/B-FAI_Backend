"""
Configuration module for B-FAI backend
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = "postgresql://bfai_user:bfai_password@db:5432/bfai_db"
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_NAME: str = "bfai_db"
    DB_USER: str = "bfai_user"
    DB_PASSWORD: str = "bfai_password"

    # Seoul Open API
    SEOUL_OPEN_API_KEY: str = "7854767a417373733432534e426264"
    SEOUL_REALTIME_API_KEY: str = "7272794a6b7373733131324f505a7471"

    # OpenAI
    OPENAI_API_KEY: str = ""

    # FastAPI
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    PROJECT_NAME: str = "B-FAI (비파이) 실시간 길안내 서비스"
    VERSION: str = "1.0.0"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
    ]

    # Cache
    API_CACHE_DURATION_MINUTES: int = 5

    # RAG
    CHROMA_DB_PATH: str = "./data/chromadb"
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
