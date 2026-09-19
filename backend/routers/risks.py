"""风险台账：默认最新完成批次；每客户最新状态视图；筛选与导出。"""
import io
import urllib.parse

import openpyxl
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import db
from logic import LEVEL_RANK

router = APIRouter(prefix="/api/risks", tags=["risks"])

EXPORT_HEADERS = ["客户名称", "风险类型", "风险等级", "风险标题", "风险描述", "风险日期", "信息来源", "扫描日期"]


def _select_records(conn, view: str, batch_id: int, level: str, risk_type: str, q: str):
    """返回 (records[list of dict], used_batch dict|None)。已按等级+客户排序，未分页。"""
    used_batch = None
    if view == "customer_latest":
        rows = conn.execute(
            """
            SELECT rr.*, sb.scan_date AS scan_date FROM risk_records rr
            JOIN scan_batches sb ON sb.id = rr.batch_id
            JOIN (
                SELECT customer_id, MAX(batch_id) AS mb FROM scan_items
                WHERE outcome IN ('有风险','无风险') AND customer_id IS NOT NULL
                GROUP BY customer_id
            ) t ON rr.batch_id = t.mb AND rr.customer_id = t.customer_id
            """
        ).fetchall()
    else:
        if batch_id:
            b = conn.execute("SELECT * FROM scan_batches WHERE id=?", (batch_id,)).fetchone()
            used_batch = dict(b) if b else None
        else:
            b = conn.execute(
                "SELECT * FROM scan_batches WHERE status='完成' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            used_batch = dict(b) if b else None
        if not used_batch:
            return [], None
        rows = conn.execute(
            "SELECT rr.*, sb.scan_date AS scan_date FROM risk_records rr "
            "JOIN scan_batches sb ON sb.id = rr.batch_id WHERE rr.batch_id=?",
            (used_batch["id"],),
        ).fetchall()
    records = [dict(r) for r in rows]
    if level:
        records = [r for r in records if r["level"] == level]
    if risk_type:
        records = [r for r in records if r["risk_type"] == risk_type]
    if q.strip():
        qq = q.strip()
        records = [
            r
            for r in records
            if qq in r["customer_name"] or qq in r["title"] or qq in r["description"]
        ]
    records.sort(
        key=lambda r: (LEVEL_RANK.get(r["level"], 9), r["customer_name"], -(r["id"] or 0))
    )
    return records, used_batch


@router.get("")
def list_risks(
    view: str = "latest_batch",
    batch_id: int = 0,
    level: str = "",
    risk_type: str = "",
    q: str = "",
    page: int = 1,
    page_size: int = 20,
):
    conn = db.connect()
    try:
        records, used_batch = _select_records(conn, view, batch_id, level, risk_type, q)
    finally:
        conn.close()
    total = len(records)
    page, page_size = max(page, 1), max(min(page_size, 200), 1)
    start = (page - 1) * page_size
    return {
        "total": total,
        "items": records[start : start + page_size],
        "batch": used_batch,
    }


@router.get("/export")
def export_risks(
    view: str = "latest_batch",
    batch_id: int = 0,
    level: str = "",
    risk_type: str = "",
    q: str = "",
):
    conn = db.connect()
    try:
        records, _ = _select_records(conn, view, batch_id, level, risk_type, q)
    finally:
        conn.close()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "风险台账"
    ws.append(EXPORT_HEADERS)
    for r in records:
        ws.append(
            [
                r["customer_name"], r["risk_type"], r["level"], r["title"],
                r["description"], r["risk_date"], r["source"], r["scan_date"],
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = urllib.parse.quote("风险台账.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
