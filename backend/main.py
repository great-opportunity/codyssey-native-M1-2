"""FastAPI 진입점. 실행: uvicorn main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import get_store
from app.routers import chat, conversations, data

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()  # 키가 잘못됐으면 서버 시작 시점에 바로 알 수 있게
    yield


app = FastAPI(
    title="My Data AI Assistant API",
    description="내 시계열 데이터(BTC 일별 종가)를 이해하고 대답하는 AI 비서 백엔드",
    version="1.0.0",
    lifespan=lifespan,
)

# 브라우저는 다른 도메인(Vercel → Render) 요청을 기본 차단한다.
# 허용할 프론트 주소만 ALLOWED_ORIGINS 환경 변수로 열어 준다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # 예상 못 한 에러도 내부 정보(키·경로 등)를 노출하지 않고 일정한 형태로 응답
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


@app.get("/", tags=["health"], summary="헬스 체크 (콜드스타트 깨우기용)")
def health():
    return {"status": "ok", "storage": settings.STORAGE, "docs": "/docs"}
