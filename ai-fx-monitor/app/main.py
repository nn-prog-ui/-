from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database.db import init_db
from app.web.routes import router

app = FastAPI(
    title="AI FX市場監視システム",
    description="FX市場の分析・通知・承認履歴保存システム（注文機能なし）",
    version="0.1.0",
)

static_dir = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    init_db()
