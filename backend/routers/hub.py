"""智能中台 API：数据源管理、数据集、数据导入、规则引擎、平台监控。"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import platform_hub as hub

router = APIRouter(prefix="/api/hub", tags=["hub"])


class SourceBody(BaseModel):
    name: str
    dstype: str = "sqlite"
    config: dict = {}
    enabled: bool = True
    note: str = ""


class SetBody(BaseModel):
    source_id: int
    name: str
    query: str
    mapping: dict = {}
    kind: str = "客户名单"
    note: str = ""


class RuleBody(BaseModel):
    name: str
    target: str = "客户"
    field: str = ""
    op: str = "contains"
    value: str = ""
    level: str = "中"
    risk_type: str = "其他"
    enabled: bool = True
    note: str = ""


@router.get("/sources")
def list_sources():
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM data_sources ORDER BY id DESC").fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/sources")
def create_source(body: SourceBody):
    if body.dstype not in hub.SUPPORTED_SOURCE_TYPES:
        raise HTTPException(400, f"类型只支持 {'/'.join(hub.SUPPORTED_SOURCE_TYPES)}")
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO data_sources(name, dstype, config, enabled, note) VALUES(?,?,?,?,?)",
            (body.name.strip(), body.dstype, json.dumps(body.config, ensure_ascii=False),
             1 if body.enabled else 0, body.note.strip()),
        )
        conn.commit()
        hub.log_event("新建数据源", f"{body.name}({body.dstype})")
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@router.put("/sources/{sid}")
def update_source(sid: int, body: SourceBody):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE data_sources SET name=?, dstype=?, config=?, enabled=?, note=? WHERE id=?",
            (body.name.strip(), body.dstype, json.dumps(body.config, ensure_ascii=False),
             1 if body.enabled else 0, body.note.strip(), sid),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/sources/{sid}")
def delete_source(sid: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM data_sets WHERE source_id=?", (sid,))
        conn.execute("DELETE FROM data_sources WHERE id=?", (sid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/sources/{sid}/test")
def test_source(sid: int):
    conn = db.connect()
    try:
        src = conn.execute("SELECT * FROM data_sources WHERE id=?", (sid,)).fetchone()
        if not src:
            raise HTTPException(404, "数据源不存在")
        try:
            msg = hub.test_source(src["dstype"], json.loads(src["config"] or "{}"))
            conn.execute("UPDATE data_sources SET last_status=? WHERE id=?", (msg, sid))
            conn.commit()
            return {"ok": True, "message": msg}
        except Exception as e:
            conn.execute("UPDATE data_sources SET last_status=? WHERE id=?", (f"失败：{e}", sid))
            conn.commit()
            return {"ok": False, "message": str(e)}
    finally:
        conn.close()


@router.get("/sets")
def list_sets(source_id: int = 0):
    conn = db.connect()
    try:
        if source_id:
            rows = conn.execute("SELECT * FROM data_sets WHERE source_id=? ORDER BY id DESC", (source_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM data_sets ORDER BY id DESC").fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/sets")
def create_set(body: SetBody):
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO data_sets(source_id, name, query, mapping, kind, note) VALUES(?,?,?,?,?,?)",
            (body.source_id, body.name.strip(), body.query, json.dumps(body.mapping, ensure_ascii=False),
             body.kind, body.note.strip()),
        )
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@router.delete("/sets/{did}")
def delete_set(did: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM data_sets WHERE id=?", (did,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/sets/{did}/preview")
def preview_set(did: int, limit: int = 20):
    conn = db.connect()
    try:
        ds = conn.execute("SELECT * FROM data_sets WHERE id=?", (did,)).fetchone()
        if not ds:
            raise HTTPException(404, "数据集不存在")
        src = conn.execute("SELECT * FROM data_sources WHERE id=?", (ds["source_id"],)).fetchone()
        if not src:
            raise HTTPException(404, "数据源不存在")
        try:
            return hub.run_query(src["dstype"], json.loads(src["config"] or "{}"), ds["query"], limit=limit)
        except Exception as e:
            raise HTTPException(400, f"查询失败：{e}")
    finally:
        conn.close()


@router.post("/sets/{did}/import-customers")
def import_customers(did: int):
    ds = db.connect()
    try:
        row = ds.execute("SELECT source_id FROM data_sets WHERE id=?", (did,)).fetchone()
        if not row:
            raise HTTPException(404, "数据集不存在")
        sid = row["source_id"]
    finally:
        ds.close()
    org = db.get_settings().get("default_org") or "本公司"
    try:
        return hub.import_customers(sid, did, org)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/rules")
def list_rules():
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM risk_rules ORDER BY id DESC").fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/rules")
def create_rule(body: RuleBody):
    if body.op not in hub.OPS:
        raise HTTPException(400, f"操作符只支持 {'/'.join(hub.OPS.keys())}")
    if body.level not in ("高", "中", "低"):
        raise HTTPException(400, "等级须为高/中/低")
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO risk_rules(name, target, field, op, value, level, risk_type, enabled, note) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (body.name.strip(), body.target, body.field.strip(), body.op, body.value,
             body.level, body.risk_type, 1 if body.enabled else 0, body.note.strip()),
        )
        conn.commit()
        hub.log_event("新建风控规则", body.name)
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@router.put("/rules/{rid}")
def update_rule(rid: int, body: RuleBody):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE risk_rules SET name=?, target=?, field=?, op=?, value=?, level=?, risk_type=?, enabled=?, note=? WHERE id=?",
            (body.name.strip(), body.target, body.field.strip(), body.op, body.value,
             body.level, body.risk_type, 1 if body.enabled else 0, body.note.strip(), rid),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/rules/{rid}")
def delete_rule(rid: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM risk_rules WHERE id=?", (rid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/rules/test")
def test_rule(body: RuleBody, customer_id: int = 0):
    """用指定客户（或首个客户）试算规则是否命中。"""
    conn = db.connect()
    try:
        if customer_id:
            c = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        else:
            c = conn.execute("SELECT * FROM customers ORDER BY id LIMIT 1").fetchone()
        if not c:
            raise HTTPException(400, "没有客户可试算")
        rule = {"field": body.field, "op": body.op, "value": body.value, "enabled": 1}
        hit = hub.match_rule(rule, dict(c))
        return {"customer": c["name"], "hit": hit, "level": body.level, "risk_type": body.risk_type}
    finally:
        conn.close()


@router.get("/logs")
def list_logs(page: int = 1, page_size: int = 50, level: str = ""):
    conn = db.connect()
    try:
        where, params = "", []
        if level:
            where, params = "WHERE level=?", [level]
        total = conn.execute(f"SELECT COUNT(*) AS c FROM platform_logs {where}", params).fetchone()["c"]
        page, page_size = max(page, 1), max(min(page_size, 200), 1)
        rows = conn.execute(
            f"SELECT * FROM platform_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/dashboard")
def hub_dashboard():
    """平台运行概览：数据规模 + 最近批次 + 日志统计（运维监控看板）。"""
    conn = db.connect()
    try:
        stat = lambda sql: conn.execute(sql).fetchone()[0]
        recent = conn.execute("SELECT * FROM scan_batches ORDER BY id DESC LIMIT 5").fetchall()
        logs_by_level = {r["level"]: r["c"] for r in conn.execute(
            "SELECT level, COUNT(*) AS c FROM platform_logs GROUP BY level").fetchall()}
        return {
            "customers": stat("SELECT COUNT(*) FROM customers"),
            "batches": stat("SELECT COUNT(*) FROM scan_batches"),
            "risk_records": stat("SELECT COUNT(*) FROM risk_records"),
            "reports": stat("SELECT COUNT(*) FROM risk_reports"),
            "sources": stat("SELECT COUNT(*) FROM data_sources"),
            "rules": stat("SELECT COUNT(*) FROM risk_rules"),
            "recent_batches": [dict(r) for r in recent],
            "logs_by_level": logs_by_level,
        }
    finally:
        conn.close()
