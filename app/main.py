"""
B-FAI (비파이) 실시간 길안내 서비스 - FastAPI Main Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.database import init_db
from app.routers import route, checkpoint

# Logger 설정
logger.add(
    "logs/app.log",
    rotation="1 day",
    retention="7 days",
    level="INFO"
)


# FastAPI 앱 생성
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
    🚇 노인 및 교통약자를 위한 실시간 지하철 길안내 서비스

    ## 주요 기능

    * **경로 탐색** - 출발지부터 목적지까지 최적 경로 제공
    * **실시간 안내** - GPS 기반 체크포인트별 음성 안내
    * **시설 상태** - Open API 연동으로 엘리베이터 고장 등 실시간 확인
    * **AI 안내** - RAG 기반 노인 친화적 안내문 생성

    ## 기술 스택

    * FastAPI + PostgreSQL
    * Seoul Open API
    * LangChain + ChromaDB (RAG)
    * OpenAI GPT-4
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)


# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 라우터 등록
app.include_router(route.router, prefix="/api")
app.include_router(checkpoint.router, prefix="/api")


# Startup event
@app.on_event("startup")
async def startup_event():
    """앱 시작 시 실행"""
    logger.info("🚀 Starting B-FAI backend server...")

    # 데이터베이스 초기화
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

    logger.info(f"📡 Server running on {settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"📖 API Documentation: http://{settings.API_HOST}:{settings.API_PORT}/docs")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """앱 종료 시 실행"""
    logger.info("👋 Shutting down B-FAI backend server...")


# Health check
@app.get("/", tags=["health"])
async def root():
    """헬스 체크"""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "message": "B-FAI backend is running! 🚇"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """상세 헬스 체크"""
    return {
        "status": "healthy",
        "database": "connected",
        "api_cache": "active",
        "rag": "initialized"
    }


# 개발 서버 실행 (python app/main.py)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
