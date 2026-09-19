"""系统配置：AI 接口、联网搜索、扫描周期、自动扫描、可配单价、用量统计。"""
import time

from fastapi import APIRouter
from pydantic import BaseModel

import ai_client
import db
import search as search_mod

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE_KEYS = {
    "default_org",
    "ai_base_url", "ai_api_key", "ai_model",
    "search_enabled", "search_api_key",
    "cycle_high", "cycle_mid", "cycle_low",
    "auto_scan_enabled", "auto_scan_time",
    "price_in", "price_out", "price_search",
    "datasource",
}


class SettingsBody(BaseModel):
    values: dict


@router.get("")
def get_all():
    settings = db.get_settings()
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS batches, COALESCE(SUM(tokens_in),0) AS tokens_in, "
            "COALESCE(SUM(tokens_out),0) AS tokens_out, COALESCE(SUM(search_count),0) AS searches, "
            "COALESCE(SUM(est_cost),0) AS est_cost FROM scan_batches"
        ).fetchone()
    finally:
        conn.close()
    return {
        "settings": settings,
        "usage": {
            "batches": row["batches"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "searches": row["searches"],
            "est_cost": round(row["est_cost"], 2),
        },
    }


@router.post("")
def save(body: SettingsBody):
    values = {k: str(v) for k, v in body.values.items() if k in EDITABLE_KEYS}
    if values:
        db.update_settings(values)
    return {"ok": True, "updated": list(values.keys())}


@router.post("/test-ai")
def test_ai():
    settings = db.get_settings()
    t0 = time.time()
    ok, message = ai_client.ping(settings)
    return {"ok": ok, "message": message, "latency_ms": int((time.time() - t0) * 1000)}


@router.post("/test-search")
def test_search():
    settings = db.get_settings()
    key = settings.get("search_api_key") or ""
    if not key:
        return {"ok": False, "message": "请先填写博查 API Key"}
    try:
        results = search_mod.bocha_search(key, "风控测试", count=1)
        return {"ok": True, "message": f"搜索正常，返回 {len(results)} 条结果"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"搜索失败：{e}"}
