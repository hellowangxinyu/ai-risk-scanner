"""系统配置：AI 接口、联网搜索、扫描周期、自动扫描、可配单价、余额与模型列表、用量统计。"""
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

import ai_client
import db
import search as search_mod

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE_KEYS = {
    "default_org",
    "ai_base_url", "ai_api_key", "ai_model",
    "search_enabled", "search_provider", "search_api_key",
    "cycle_high", "cycle_mid", "cycle_low",
    "auto_scan_enabled", "auto_scan_time",
    "price_in", "price_out", "price_search",
    "datasource",
}


def _base_without_v1(settings: dict) -> str:
    """辅助接口（余额/模型列表）官方地址不含 /v1，兼容用户配置里带 /v1 的写法。"""
    base = (settings.get("ai_base_url") or "").rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


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
    if settings.get("search_enabled") != "1":
        return {"ok": False, "message": "联网搜索当前未启用，请先打开开关并保存"}
    provider = settings.get("search_provider") or "deepseek"
    try:
        if provider == "deepseek":
            results, _, _ = search_mod.deepseek_search(
                settings.get("ai_api_key") or "", "DeepSeek 风控 测试", max_uses=1
            )
            return {"ok": True, "message": f"DeepSeek 原生搜索正常，返回 {len(results)} 条结果"}
        key = settings.get("search_api_key") or ""
        if not key:
            return {"ok": False, "message": "请先填写博查 API Key"}
        results = search_mod.bocha_search(key, "风控测试", count=1)
        return {"ok": True, "message": f"博查搜索正常，返回 {len(results)} 条结果"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"搜索失败：{e}"}


@router.post("/balance")
def query_balance():
    """查询 DeepSeek 账户余额（GET /user/balance，按币种返回）。"""
    settings = db.get_settings()
    key = settings.get("ai_api_key") or ""
    if not key:
        return {"ok": False, "message": "请先填写 AI API Key"}
    url = _base_without_v1(settings) + "/user/balance"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if r.status_code != 200:
            return {"ok": False, "message": f"接口返回 {r.status_code}：{r.text[:200]}"}
        data = r.json()
        return {
            "ok": True,
            "is_available": bool(data.get("is_available")),
            "balances": data.get("balance_infos") or [],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"查询失败：{e}"}


@router.post("/models")
def list_models():
    """获取当前服务可用的模型列表（GET /models）。"""
    settings = db.get_settings()
    key = settings.get("ai_api_key") or ""
    if not key:
        return {"ok": False, "message": "请先填写 AI API Key"}
    url = _base_without_v1(settings) + "/models"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if r.status_code != 200:
            return {"ok": False, "message": f"接口返回 {r.status_code}：{r.text[:200]}"}
        data = r.json()
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return {"ok": True, "models": ids}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"查询失败：{e}"}
