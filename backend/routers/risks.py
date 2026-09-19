"""风险台账：默认最新完成批次；每客户最新状态视图；筛选与导出。"""
import io
import urllib.parse

import openpyxl
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import db
from logic import LEVEL_RANK, compute_lifecycle

router = APIRouter(prefix="/api/risks", tags=["risks"])

EXPORT_HEADERS = ["客户名称", "是否授信", "客户类型", "风险类型", "风险等级", "风险标题", "风险描述", "风险日期", "信息来源", "扫描日期", "批次"]
LIFECYCLE_HEADERS = ["客户名称", "风险类型", "当前等级", "风险标题", "风险描述", "首次发现", "最近确认", "出现批次数", "状态"]


def _latest_valid_batch(conn) -> dict:
    """每客户最近一次有效扫描（有风险/无风险）的批次，键为 ("id", customer_id)。"""
    rows = conn.execute(
        "SELECT customer_id AS cid, MAX(batch_id) AS mb FROM scan_items "
        "WHERE outcome IN ('有风险','无风险') AND customer_id IS NOT NULL GROUP BY customer_id"
    ).fetchall()
    return {("id", r["cid"]): r["mb"] for r in rows}


def _lifecycle_items(conn, level: str, risk_type: str, q: str) -> list:
    rows = conn.execute(
        "SELECT rr.*, sb.scan_date AS scan_date FROM risk_records rr "
        "JOIN scan_batches sb ON sb.id = rr.batch_id"
    ).fetchall()
    items = compute_lifecycle([dict(r) for r in rows], _latest_valid_batch(conn))
    if level:
        items = [i for i in items if i["level"] == level]
    if risk_type:
        items = [i for i in items if i["risk_type"] == risk_type]
    if q.strip():
        qq = q.strip()
        items = [i for i in items if qq in i["customer_name"] or qq in i["title"] or qq in (i["description"] or "")]
    return items


def _enrich(conn, records: list) -> list:
    """给风险记录补客户属性列（是否授信/客户类型），用于客户分析；客户已删除时留空。"""
    for r in records:
        c = conn.execute(
            "SELECT ctype, is_credit FROM customers WHERE id=?", (r["customer_id"],)
        ).fetchone() if r["customer_id"] is not None else None
        r["ctype"] = c["ctype"] if c else ""
        r["is_credit"] = "是" if (c and c["is_credit"]) else ("否" if c else "")
    return records


def _build_workbook(records: list, headers=None, rows_builder=None) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "风险台账"
    ws.append(headers or EXPORT_HEADERS)
    for r in records:
        ws.append(rows_builder(r) if rows_builder else [
            r["customer_name"], r.get("is_credit", ""), r.get("ctype", ""),
            r["risk_type"], r["level"], r["title"], r["description"],
            r["risk_date"], r["source"], r["scan_date"], r["batch_id"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@router.get("/export")
def export_risks(
    view: str = "latest_batch",
    batch_id: int = 0,
    level: str = "",
    risk_type: str = "",
    q: str = "",
    date: str = "",
    full: int = 0,
):
    """导出风险台账。

    - view=lifecycle：风险项生命周期视图（去重清单，含首次发现/最近确认/出现批次数/状态）；
    - date=YYYY-MM-DD：按扫描日期全量导出该日期所有批次的全部风险记录（不套用视图与筛选）；
    - full=1：全量导出全部历史风险记录；
    - 两者都不传：按当前视图与筛选条件导出。
    """
    if view == "lifecycle":
        conn = db.connect()
        try:
            items = _lifecycle_items(conn, level, risk_type, q)
        finally:
            conn.close()
        buf = _build_workbook(
            items, headers=LIFECYCLE_HEADERS,
            rows_builder=lambda r: [
                r["customer_name"], r["risk_type"], r["level"], r["title"],
                r["description"], r["first_seen"], r["last_seen"],
                r["batch_count"], r["status"],
            ],
        )
        filename = urllib.parse.quote("风险台账-风险项生命周期.xlsx")
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    conn = db.connect()
    try:
        if date or full:
            where, params = "", []
            if date:
                where = "WHERE substr(sb.scan_date, 1, 10) = ?"
                params = [date]
            rows = conn.execute(
                "SELECT rr.*, sb.scan_date AS scan_date FROM risk_records rr "
                f"JOIN scan_batches sb ON sb.id = rr.batch_id {where} "
                "ORDER BY sb.scan_date DESC, rr.customer_name, "
                "CASE rr.level WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END",
                params,
            ).fetchall()
            records = _enrich(conn, [dict(r) for r in rows])
        else:
            raw, _ = _select_records(conn, view, batch_id, level, risk_type, q)
            records = _enrich(conn, raw)
    finally:
        conn.close()
    buf = _build_workbook(records)
    filename = urllib.parse.quote(
        f"风险台账-{date}.xlsx" if date else "风险台账-全部历史.xlsx"
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


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
    if view == "lifecycle":
        conn = db.connect()
        try:
            items = _lifecycle_items(conn, level, risk_type, q)
        finally:
            conn.close()
        total = len(items)
        page, page_size = max(page, 1), max(min(page_size, 200), 1)
        start = (page - 1) * page_size
        return {"total": total, "items": items[start : start + page_size], "batch": None}

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
