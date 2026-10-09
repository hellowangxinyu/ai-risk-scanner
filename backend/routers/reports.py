"""每日风险报告：列表与详情。"""
import json

from fastapi import APIRouter, HTTPException

import db

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(page: int = 1, page_size: int = 20):
    conn = db.connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM risk_reports").fetchone()["c"]
        page, page_size = max(page, 1), max(min(page_size, 100), 1)
        rows = conn.execute(
            "SELECT * FROM risk_reports ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/{rid}")
def get_report(rid: int):
    conn = db.connect()
    try:
        r = conn.execute("SELECT * FROM risk_reports WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "报告不存在")
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        return d
    finally:
        conn.close()
