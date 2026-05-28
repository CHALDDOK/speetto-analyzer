"""
스피또 당첨 확률 분석기 - 서버 메인 파일
========================================
FastAPI로 만든 백엔드 서버입니다.
- /api/data  : 동행복권 스피또 데이터 반환 (60분 캐싱)
- /api/health: 서버 상태 확인
- /          : 프론트엔드 웹페이지
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import os

app = FastAPI(title="스피또 분석기 API")

# 어디서든 접근 가능하도록 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── 메모리 캐시 ──────────────────────────────────────────────
_cache = {
    "data": None,
    "updated_at": None,
}
CACHE_MINUTES = 60  # 60분마다 새로 수집


@app.get("/api/data")
async def get_data():
    """스피또 발행내역 데이터를 반환합니다. 60분 캐싱."""
    global _cache
    now = datetime.now()

    needs_refresh = (
        _cache["data"] is None
        or (now - _cache["updated_at"]) > timedelta(minutes=CACHE_MINUTES)
    )

    if needs_refresh:
        try:
            from scraper import scrape_speitto_data
            data = await scrape_speitto_data()
            if data:  # 데이터가 있을 때만 캐시 갱신
                _cache = {"data": data, "updated_at": now}
        except Exception as e:
            print(f"[ERROR] 스크래핑 실패: {e}")
            if _cache["data"] is None:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "데이터 수집에 실패했습니다.",
                        "detail": str(e),
                    },
                )
            # 실패해도 기존 캐시 반환 (오류보다 낫다)

    return {
        "data": _cache["data"],
        "updated_at": (
            _cache["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
            if _cache["updated_at"] else None
        ),
        "total": len(_cache["data"]) if _cache["data"] else 0,
    }


@app.get("/api/health")
async def health():
    """서버 상태 확인용 엔드포인트."""
    return {
        "status": "ok",
        "has_cache": _cache["data"] is not None,
        "cache_age_minutes": (
            round((datetime.now() - _cache["updated_at"]).seconds / 60)
            if _cache["updated_at"] else None
        ),
    }


# 정적 파일 서빙 (프론트엔드 HTML/CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """메인 페이지 반환."""
    return FileResponse("static/index.html")
