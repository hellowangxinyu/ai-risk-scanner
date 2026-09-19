"""风险扫描：发起、进度轮询、批次管理（删除/重扫）。"""
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from logic import ScanError
from scanner import _aggregate, list_customers_with_due, start_batch

router = APIRouter(prefix="/api/scan", tags=["scan"])


class StartBody(BaseModel):
    customer_ids: List[int]


@router.post("/start")
def start(body: StartBody):
    try:
        batch_id = start_batch(body.customer_ids, trigger="手动")
    except ScanError as e:
        raise HTTPException(409, str(e))
    return {"batch_id": batch_id}


@router.get("/current")
def current():
    """当前运行中批次（供页面刷新后恢复轮询）。"""
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM scan_batches WHERE status IN ('待运行','运行中') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"batch": None}
        agg = _aggregate(conn, row["id"])
        items = conn.execute(
            "SELECT customer_name, outcome FROM scan_items WHERE batch_id=? ORDER BY id", (row["id"],)
        ).fetchall()
        current_name = next(
            (i["customer_name"] for i in items if i["outcome"] == "待处理"), ""
        )
        return {
            "batch": dict(row),
            "progress": {
                "total": len(items),
                "done": agg["done"],
                "failed": agg["failed"],
                "risk_count": agg["risk_count"],
                "tokens_in": agg["tokens_in"],
                "tokens_out": agg["tokens_out"],
                "est_cost": agg["est_cost"],
                "current": current_name,
            },
        }
    finally:
        conn.close()


@router.get("/batches")
def batches(limit: int = 50):
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM scan_batches ORDER BY id DESC LIMIT ?", (min(limit, 200),)
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.delete("/batches/{bid}")
def delete_batch(bid: int):
    conn = db.connect()
    try:
        row = conn.execute("SELECT status FROM scan_batches WHERE id=?", (bid,)).fetchone()
        if not row:
            raise HTTPException(404, "批次不存在")
        if row["status"] in ("待运行", "运行中"):
            raise HTTPException(400, "批次正在运行，不能删除")
        conn.execute("DELETE FROM risk_records WHERE batch_id=?", (bid,))
        conn.execute("DELETE FROM scan_items WHERE batch_id=?", (bid,))
        conn.execute("DELETE FROM scan_batches WHERE id=?", (bid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/batches/{bid}/rescan")
def rescan_batch(bid: int):
    """按原客户清单发起新批次（风险记录按批次隔离，不做覆盖式重扫）。"""
    conn = db.connect()
    try:
        ids = [
            r["customer_id"]
            for r in conn.execute(
                "SELECT DISTINCT customer_id FROM scan_items WHERE batch_id=? "
                "AND customer_id IS NOT NULL ORDER BY customer_id",
                (bid,),
            ).fetchall()
        ]
        ids = [
            cid
            for cid in ids
            if conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
        ]
    finally:
        conn.close()
    if not ids:
        raise HTTPException(400, "原批次客户均已不存在，无法重扫")
    try:
        new_id = start_batch(ids, trigger="手动")
    except ScanError as e:
        raise HTTPException(409, str(e))
    return {"batch_id": new_id, "count": len(ids)}


@router.get("/due-preview")
def due_preview():
    items = list_customers_with_due()
    due = [c["id"] for c in items if c["due"]]
    return {"due_ids": due, "due_count": len(due)}
