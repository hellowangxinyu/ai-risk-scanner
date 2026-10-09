"""智能中台核心：外部数据源接入、数据集映射、自定义规则引擎、平台监控。

依赖安装（MySQL/PostgreSQL 支持为可选，装了 drivers 才可用）：
  pip install pymysql psycopg2-binary
"""
import json
import sqlite3

SUPPORTED_SOURCE_TYPES = ("sqlite", "mysql", "postgresql")


def log_event(event: str, detail: str = "", level: str = "INFO"):
    """平台运行日志（运维监控）。"""
    import db

    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO platform_logs(level, event, detail) VALUES(?,?,?)",
            (level, event, str(detail)[:4000]),
        )
        conn.commit()
    finally:
        conn.close()


def _connect(dstype: str, config: dict):
    """按类型建立外部数据库连接（MySQL/PostgreSQL 需可选驱动）。"""
    if dstype == "sqlite":
        path = (config.get("path") or "").strip()
        if not path:
            raise ValueError("sqlite 数据源需提供 path（数据库文件路径）")
        return sqlite3.connect(path)
    if dstype == "mysql":
        try:
            import pymysql
        except ImportError:
            raise ValueError("MySQL 支持需安装驱动：pip install pymysql")
        return pymysql.connect(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 3306)),
            user=config.get("user", ""),
            password=config.get("password", ""),
            database=config.get("database", ""),
        )
    if dstype == "postgresql":
        try:
            import psycopg2
        except ImportError:
            raise ValueError("PostgreSQL 支持需安装驱动：pip install psycopg2-binary")
        return psycopg2.connect(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 5432)),
            user=config.get("user", ""),
            password=config.get("password", ""),
            dbname=config.get("database", ""),
        )
    raise ValueError(f"不支持的数据源类型：{dstype}")


def test_source(dstype: str, config: dict) -> str:
    """测试数据源连通性，返回状态描述。"""
    conn = _connect(dstype, config)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        return "连接成功"
    finally:
        conn.close()


def run_query(dstype: str, config: dict, query: str, limit: int = 100) -> dict:
    """执行数据集查询（只读），返回 {columns, rows}。行数截断到 limit。"""
    conn = _connect(dstype, config)
    try:
        conn.row_factory = sqlite3.Row if dstype == "sqlite" else None
        cur = conn.cursor()
        cur.execute(query)
        cols = [d[0] for d in (cur.description or [])]
        raw = cur.fetchall()
        rows = []
        for r in raw[:limit]:
            if isinstance(r, sqlite3.Row):
                rows.append([r[c] for c in cols])
            else:
                rows.append(list(r))
        return {"columns": cols, "rows": rows, "truncated": len(raw) > limit, "total": len(raw)}
    finally:
        conn.close()


def import_customers(source_id: int, data_set_id: int, default_org: str = "本公司") -> dict:
    """数据集 → 客户表（多源数据采集）：按 mapping 把查询结果的列映射到客户字段。

    mapping 形如 {"名称": "customer_name", "类型": "ctype", "统一社会信用代码": "credit_code"}。
    返回 {created, skipped, failed:[{row, reason}]}。
    """
    import db
    from logic import parse_credit_flag, validate_import_row

    conn = db.connect()
    try:
        src = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
        ds = conn.execute("SELECT * FROM data_sets WHERE id=?", (data_set_id,)).fetchone()
        if not src or not ds:
            raise ValueError("数据源或数据集不存在")
        config = json.loads(src["config"] or "{}")
        mapping = json.loads(ds["mapping"] or "{}")
        result = run_query(src["dstype"], config, ds["query"], limit=5000)
        cols, rows = result["columns"], result["rows"]

        def col(field):
            for k, v in mapping.items():
                if v == field:
                    return cols.index(k) if k in cols else None
            return None

        idx = {
            "name": col("name"), "ctype": col("ctype"), "credit_code": col("credit_code"),
            "contact": col("contact"), "note": col("note"), "is_credit": col("is_credit"),
        }
        report = {"created": 0, "skipped": 0, "failed": []}
        seen = set()
        for i, row in enumerate(rows, start=1):
            def val(field):
                j = idx[field]
                return "" if j is None or j >= len(row) or row[j] is None else row[j]

            ok, fields, reason = validate_import_row(
                val("name"), val("ctype") or "公司", val("credit_code"), val("contact"), val("note"))
            name = str(val("name") or "").strip()
            if not ok:
                report["failed"].append({"row": i, "name": name, "reason": reason})
                continue
            if idx["is_credit"] is not None:
                try:
                    fields["is_credit"] = 1 if parse_credit_flag(val("is_credit")) else 0
                except ValueError as e:
                    report["failed"].append({"row": i, "name": name, "reason": str(e)})
                    continue
            else:
                fields["is_credit"] = 0
            if fields["name"] in seen:
                report["skipped"] += 1
                continue
            dup = conn.execute(
                "SELECT id FROM customers WHERE org=? AND name=?", (default_org, fields["name"])
            ).fetchone()
            if dup:
                report["skipped"] += 1
                continue
            conn.execute(
                "INSERT INTO customers(org, name, ctype, credit_code, contact, note, is_credit, last_risk_level) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (default_org, fields["name"], fields["ctype"], fields["credit_code"],
                 fields["contact"], fields["note"], fields["is_credit"],
                 "高" if fields["is_credit"] else "低"),
            )
            seen.add(fields["name"])
            report["created"] += 1
        status = "导入客户 {} 成功 / {} 跳过 / {} 失败".format(
            report["created"], report["skipped"], len(report["failed"]))
        conn.execute(
            "UPDATE data_sources SET last_sync_at=datetime('now','localtime'), last_status=? WHERE id=?",
            (status, source_id),
        )
        conn.commit()
        log_event("数据集导入客户", f"数据集#{data_set_id} → 新建{report['created']} 跳过{report['skipped']} 失败{len(report['failed'])}")
        return report
    finally:
        conn.close()


# ---------- 规则引擎（不用 AI，按字段规则判风险） ----------

OPS = {
    "contains": lambda v, t: str(t) in str(v),
    "not_contains": lambda v, t: str(t) not in str(v),
    "eq": lambda v, t: str(v).strip() == str(t).strip(),
    "ne": lambda v, t: str(v).strip() != str(t).strip(),
    "gt": lambda v, t: _num(v) > _num(t),
    "lt": lambda v, t: _num(v) < _num(t),
    "empty": lambda v, t: str(v or "").strip() == "",
    "not_empty": lambda v, t: str(v or "").strip() != "",
}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def match_rule(rule: dict, customer: dict) -> bool:
    field = rule.get("field", "")
    fn = OPS.get(rule.get("op", "contains"))
    if not fn:
        return False
    return fn(customer.get(field, ""), rule.get("value", ""))


def rule_risks_for_customer(customer: dict, rules: list) -> list:
    """对单个客户套用启用中的规则，返回命中的风险项（risk_type/level/title/description）。"""
    hits = []
    for r in rules:
        if not r.get("enabled"):
            continue
        if match_rule(r, customer):
            hits.append({
                "risk_type": r.get("risk_type", "其他"),
                "level": r.get("level", "中"),
                "title": f"规则命中：{r.get('name', '')}",
                "description": f"{r.get('field')} {r.get('op')} {r.get('value')}",
                "risk_date": "",
                "source": "规则引擎",
            })
    return hits


def log_rule_engine(batch_id: int, matched: int):
    log_event("规则引擎", f"批次 #{batch_id} 规则命中 {matched} 条", "INFO")
