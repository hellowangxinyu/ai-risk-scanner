"""扫描执行：批次创建即运行，逐客户串行；风险记录按批次隔离，永不覆盖。"""
import threading
from datetime import date, datetime

import db
from datasource import get_source
from logic import ScanError, is_due, max_level

LOW_CYCLE_DEFAULT = 30


def _cycles(settings: dict) -> dict:
    low = int(float(settings.get("cycle_low") or LOW_CYCLE_DEFAULT))
    return {
        "高": int(float(settings.get("cycle_high") or 3)),
        "中": int(float(settings.get("cycle_mid") or 7)),
        "低": low,
        "无": low,
    }


def list_customers_with_due() -> list:
    """全部客户 + 到期标记（授信=高档，非授信按扫描等级）+ 所属机构等（供扫描页与客户页使用）。"""
    cycles = _cycles(db.get_settings())
    today = date.today()
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["due"] = is_due(d["last_scan_at"], d["last_risk_level"], today, cycles, bool(d["is_credit"]))
        out.append(d)
    return out


def due_customer_ids() -> list:
    return [c["id"] for c in list_customers_with_due() if c["due"]]


def has_running_batch(conn=None) -> bool:
    own = conn is None
    conn = conn or db.connect()
    try:
        row = conn.execute(
            "SELECT id FROM scan_batches WHERE status IN ('待运行','运行中') LIMIT 1"
        ).fetchone()
        return row is not None
    finally:
        if own:
            conn.close()


def start_batch(customer_ids: list, trigger: str = "手动") -> int:
    """创建批次并立即在后台线程执行。已有运行中批次时抛 ScanError（护栏①）。"""
    if has_running_batch():
        raise ScanError("已有扫描任务在进行中，请等待完成后再发起")
    if not customer_ids:
        raise ScanError("请先选择要扫描的客户")
    conn = db.connect()
    try:
        rows = []
        for cid in customer_ids:
            r = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
            if r:
                rows.append(dict(r))
        if not rows:
            raise ScanError("所选客户均不存在")
        settings = db.get_settings()
        cur = conn.execute(
            "INSERT INTO scan_batches(total, status, price_in, price_out, price_search, trigger_type) "
            "VALUES(?,?,?,?,?,?)",
            (
                len(rows),
                "运行中",
                float(settings.get("price_in") or 0),
                float(settings.get("price_out") or 0),
                float(settings.get("price_search") or 0),
                trigger,
            ),
        )
        batch_id = cur.lastrowid
        for r in rows:
            conn.execute(
                "INSERT INTO scan_items(batch_id, customer_id, customer_name) VALUES(?,?,?)",
                (batch_id, r["id"], r["name"]),
            )
        conn.commit()
    finally:
        conn.close()
    threading.Thread(target=run_batch, args=(batch_id,), daemon=True).start()
    return batch_id


def run_batch(batch_id: int):
    """线程入口：任何未捕获异常都落到批次状态上，不留'运行中'孤儿。"""
    try:
        _run_batch(batch_id)
    except Exception as e:  # noqa: BLE001
        conn = db.connect()
        try:
            conn.execute(
                "UPDATE scan_batches SET status='失败', note=? WHERE id=?",
                (f"批次执行异常：{e}", batch_id),
            )
            conn.commit()
        finally:
            conn.close()


def _run_batch(batch_id: int):
    settings = db.get_settings()
    conn = db.connect()
    try:
        items = conn.execute(
            "SELECT * FROM scan_items WHERE batch_id=? ORDER BY id", (batch_id,)
        ).fetchall()
    finally:
        conn.close()

    for item in items:
        if item["outcome"] != "待处理":
            continue  # 断点续扫语义：跳过已完成项
        try:
            result = _scan_customer(item, settings)
        except ScanError as e:
            result = _failed_result(str(e))
        except Exception as e:  # noqa: BLE001
            result = _failed_result(f"未知错误：{e}")
        _persist_item(batch_id, item, result, settings)

    conn = db.connect()
    try:
        agg = _aggregate(conn, batch_id)
        status = "失败" if (agg["done"] > 0 and agg["failed"] == agg["done"]) else "完成"
        conn.execute(
            "UPDATE scan_batches SET status=? WHERE id=? AND status IN ('待运行','运行中')",
            (status, batch_id),
        )
        conn.commit()
    finally:
        conn.close()


def _failed_result(reason: str) -> dict:
    return {
        "outcome": "失败",
        "fail_reason": reason,
        "risks": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "searched": False,
        "mode": "",
        "summary": "",
    }


def _scan_customer(item, settings: dict) -> dict:
    conn = db.connect()
    try:
        cust = None
        if item["customer_id"] is not None:
            cust = conn.execute(
                "SELECT * FROM customers WHERE id=?", (item["customer_id"],)
            ).fetchone()
    finally:
        conn.close()
    if cust is None:
        raise ScanError("客户已不存在（可能在扫描前被删除）")
    return get_source(settings).assess(dict(cust), settings)


def _persist_item(batch_id: int, item, result: dict, settings: dict):
    conn = db.connect()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if result["outcome"] in ("有风险", "无风险") and item["customer_id"] is not None:
            conn.execute(
                "UPDATE customers SET last_scan_at=?, last_risk_level=? WHERE id=?",
                (now, max_level([r["level"] for r in result["risks"]]) or "无", item["customer_id"]),
            )
        if result["outcome"] == "有风险":
            for r in result["risks"]:
                conn.execute(
                    "INSERT INTO risk_records(batch_id, customer_id, customer_name, risk_type, "
                    "level, title, description, risk_date, source) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        batch_id,
                        item["customer_id"],
                        item["customer_name"],
                        r["risk_type"],
                        r["level"],
                        r["title"],
                        r["description"],
                        r.get("risk_date", ""),
                        r.get("source", ""),
                    ),
                )
        conn.execute(
            "UPDATE scan_items SET outcome=?, fail_reason=?, tokens_in=?, tokens_out=?, "
            "searched=?, mode=?, summary=? WHERE id=?",
            (
                result["outcome"],
                result.get("fail_reason", ""),
                int(result.get("tokens_in") or 0),
                int(result.get("tokens_out") or 0),
                # searched 列语义 = 按次计费的联网搜索数（博查）；
                # DeepSeek 原生搜索的成本体现在 Token 用量中，不计入搜索次数
                1 if (result.get("searched") and result.get("search_paid")) else 0,
                result.get("mode", ""),
                result.get("summary", ""),
                item["id"],
            ),
        )
        agg = _aggregate(conn, batch_id)
        conn.execute(
            "UPDATE scan_batches SET tokens_in=?, tokens_out=?, search_count=?, est_cost=?, risk_count=? "
            "WHERE id=?",
            (
                agg["tokens_in"],
                agg["tokens_out"],
                agg["search_count"],
                agg["est_cost"],
                agg["risk_count"],
                batch_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _aggregate(conn, batch_id: int) -> dict:
    b = conn.execute("SELECT * FROM scan_batches WHERE id=?", (batch_id,)).fetchone()
    items = conn.execute(
        "SELECT outcome, tokens_in, tokens_out, searched FROM scan_items WHERE batch_id=?",
        (batch_id,),
    ).fetchall()
    tokens_in = sum(i["tokens_in"] for i in items)
    tokens_out = sum(i["tokens_out"] for i in items)
    search_count = sum(1 for i in items if i["searched"])
    risk_count = conn.execute(
        "SELECT COUNT(*) AS c FROM risk_records WHERE batch_id=?", (batch_id,)
    ).fetchone()["c"]
    est = (
        tokens_in / 1e6 * (b["price_in"] or 0)
        + tokens_out / 1e6 * (b["price_out"] or 0)
        + search_count * (b["price_search"] or 0)
    )
    done = sum(1 for i in items if i["outcome"] != "待处理")
    failed = sum(1 for i in items if i["outcome"] == "失败")
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "search_count": search_count,
        "risk_count": risk_count,
        "est_cost": round(est, 4),
        "done": done,
        "failed": failed,
    }
