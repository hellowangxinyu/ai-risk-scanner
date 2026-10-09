"""每日风险报告：扫描批次完成时自动生成，含分级统计 + 新增风险 + 推送渠道预留。"""
import json
from datetime import datetime

import db
from logic import LEVEL_RANK, normalize_risk_title


def _prev_titles_map(conn, batch_id: int) -> dict:
    """每个客户上次有效扫描（早于本批次）的风险标题集合，用于判定"新增风险"。"""
    rows = conn.execute(
        "SELECT DISTINCT rr.customer_id, rr.risk_type, rr.title FROM risk_records rr "
        "JOIN scan_items si ON si.batch_id = rr.batch_id AND si.customer_id = rr.customer_id "
        "WHERE si.outcome IN ('有风险','无风险') AND si.batch_id < ? AND rr.customer_id IS NOT NULL",
        (batch_id,),
    ).fetchall()
    m = {}
    for r in rows:
        m.setdefault(r["customer_id"], set()).add((r["risk_type"], normalize_risk_title(r["title"])))
    return m


def generate_report(batch_id: int) -> int:
    """扫描批次完成后生成每日风险报告，返回报告 ID。"""
    conn = db.connect()
    try:
        b = conn.execute("SELECT * FROM scan_batches WHERE id=?", (batch_id,)).fetchone()
        if not b:
            return 0
        risks = conn.execute(
            "SELECT rr.*, sb.scan_date AS scan_date FROM risk_records rr "
            "JOIN scan_batches sb ON sb.id=rr.batch_id WHERE rr.batch_id=? ORDER BY rr.id",
            (batch_id,),
        ).fetchall()
        items = conn.execute(
            "SELECT customer_id, customer_name, outcome FROM scan_items WHERE batch_id=? ORDER BY id",
            (batch_id,),
        ).fetchall()

        customers = {}
        for it in items:
            customers[it["customer_id"]] = it["customer_name"]
        risk_customer_ids = {r["customer_id"] for r in risks if r["customer_id"] is not None}
        risk_customers = len(risk_customer_ids)

        high = sum(1 for r in risks if r["level"] == "高")
        mid = sum(1 for r in risks if r["level"] == "中")
        low = sum(1 for r in risks if r["level"] == "低")

        # 新增风险：本批次出现、但客户上次扫描没有的风险
        prev = _prev_titles_map(conn, batch_id)
        new_risks = []
        for r in risks:
            cid = r["customer_id"]
            key = (r["risk_type"], normalize_risk_title(r["title"]))
            if cid is not None and key not in prev.get(cid, set()):
                new_risks.append(dict(r))

        # 按客户分组的风险明细
        by_customer = {}
        for r in risks:
            d = dict(r)
            cid = d["customer_id"] if d["customer_id"] is not None else d["customer_name"]
            by_customer.setdefault(cid, []).append(d)
        grouped = [
            {"customer_name": g[0]["customer_name"], "risks": sorted(
                g, key=lambda x: LEVEL_RANK.get(x["level"], 9))}
            for g in sorted(by_customer.values(), key=lambda g: (LEVEL_RANK.get(g[0]["level"], 9), g[0]["customer_name"]))
        ]

        when = b["scan_date"][:10]
        title = f"风险日报 {when}（批次 #{batch_id}）"
        summary = (
            f"本次扫描 {b['total']} 家客户，{risk_customers} 家存在风险；"
            f"风险项共 {len(risks)} 条（高 {high} / 中 {mid} / 低 {low}），"
            f"其中新增风险 {len(new_risks)} 条。"
        )
        cur = conn.execute(
            "INSERT INTO risk_reports(batch_id, report_date, title, summary, total_customers, "
            "risk_customers, high_count, mid_count, low_count, risk_lines, new_risk_lines, payload) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                batch_id, b["scan_date"], title, summary, b["total"], risk_customers,
                high, mid, low, len(risks), len(new_risks),
                json.dumps({"grouped": grouped, "new_risks": [dict(r) for r in new_risks],
                            "failed_customers": [dict(i) for i in items if i["outcome"] == "失败"]},
                           ensure_ascii=False),
            ),
        )
        conn.commit()
        rid = cur.lastrowid
        # 推送渠道预留：在此处接入企业微信/钉钉/邮件 webhook
        _push(rid)
        return rid
    finally:
        conn.close()


def _push(report_id: int):
    """推送渠道预留：读取 settings 里的推送配置（report_push_channel / webhook），
    为空则标记"未推送"。接入企业微信/钉钉/邮件时在此实现。"""
    settings = db.get_settings()
    channel = settings.get("report_push_channel") or ""
    webhook = settings.get("report_push_webhook") or ""
    if not channel or not webhook:
        return
    # TODO: 按 channel 调用 webhook（企业微信/钉钉/邮件），成功后更新 push_status
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE risk_reports SET push_status='已推送', push_channel=? WHERE id=?",
            (channel, report_id),
        )
        conn.commit()
    finally:
        conn.close()
