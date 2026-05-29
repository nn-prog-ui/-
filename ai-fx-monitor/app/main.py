from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database.db import init_db
from app.web.routes import router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.auth import (
    AUTH_ENABLED,
    check_credentials,
    is_public_path,
    parse_basic_auth,
)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """AUTH_USERNAME / AUTH_PASSWORD が設定されている場合にのみ認証を要求する。"""

    async def dispatch(self, request: Request, call_next):
        if not AUTH_ENABLED or is_public_path(request.url.path):
            return await call_next(request)
        credentials = parse_basic_auth(request.headers.get("Authorization"))
        if credentials and check_credentials(*credentials):
            return await call_next(request)
        return Response(
            content="認証が必要です",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="AI FX Monitor"'},
            media_type="text/plain; charset=utf-8",
        )


app = FastAPI(
    title="AI FX市場監視システム",
    description="FX市場の分析・通知・承認履歴保存システム（注文機能なし）",
    version="0.1.0",
)

app.add_middleware(BasicAuthMiddleware)

static_dir = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    # Phase 76: 起動チェック（ディレクトリ・CSVデータ・安全環境変数）
    try:
        from app.scripts.startup_check import run_startup_checks
        run_startup_checks()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("起動チェックエラー（継続）: %s", exc)

    init_db()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()
