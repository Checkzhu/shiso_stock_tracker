"""A股每日选股追踪系统 - 主入口"""
import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, SessionLocal
from app.api import router
from app.auth import seed_default_admin
from app.scheduler import start_scheduler, stop_scheduler
import app.models  # 确保所有模型被加载以创建表

app = FastAPI(title="A股选股追踪系统", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        seed_default_admin(db)
    finally:
        db.close()
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))
