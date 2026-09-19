"""AI 财务风控系统入口：鉴权中间件 + API 路由 + 前端静态托管 + 启动初始化。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import auth
from auth import (
    AuthMiddleware,
    COOKIE_NAME,
    current_password,
    is_default_password,
    make_token,
)
from db import init_db, mark_interrupted
from routers import customers, risks, scan, settings as settings_router
from scheduler import AutoScanScheduler

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = (BASE_DIR.parent / "frontend" / "dist").resolve()

scheduler = AutoScanScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    auth.init_secret()
    n = mark_interrupted()  # 中断恢复：遗留"运行中"批次标记为"中断"
    if n:
        print(f"[startup] 已将 {n} 个遗留批次标记为中断")
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="AI 财务风控", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.include_router(customers.router)
app.include_router(scan.router)
app.include_router(risks.router)
app.include_router(settings_router.router)


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    if body.password != current_password():
        raise HTTPException(401, "口令错误")
    response.set_cookie(
        COOKIE_NAME, make_token(), httponly=True, samesite="lax",
        max_age=auth.MAX_AGE, path="/",
    )
    return {"ok": True, "default_password": is_default_password()}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/me")
def me():
    return {"ok": True, "default_password": is_default_password()}


@app.get("/{full_path:path}")
def spa(full_path: str):
    """前端 SPA 托管：文件命中返回文件，否则回退 index.html。"""
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if full_path:
        f = (DIST_DIR / full_path).resolve()
        if f.is_file() and str(f).startswith(str(DIST_DIR)):
            return FileResponse(f)
    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "前端未构建：请先在 frontend 目录执行 npm run build"}, status_code=404
    )
