"""智能中台：规则引擎与数据源（sqlite）测试。"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import platform_hub as hub


def test_ops():
    assert hub.OPS["contains"]("山东亚泰新材料", "亚泰")
    assert not hub.OPS["contains"]("山东亚泰新材料", "北京")
    assert hub.OPS["eq"]("公司", "公司")
    assert hub.OPS["ne"]("公司", "个人")
    assert hub.OPS["gt"]("100", "50")
    assert hub.OPS["lt"]("30", "50")
    assert hub.OPS["empty"]("", "x")
    assert hub.OPS["not_empty"]("abc", "")


def test_match_rule():
    cust = {"name": "山东亚泰新材料有限公司", "note": "股权已冻结", "is_credit": 1}
    assert hub.match_rule({"field": "note", "op": "contains", "value": "冻结"}, cust)
    assert not hub.match_rule({"field": "note", "op": "contains", "value": "正常"}, cust)
    assert hub.match_rule({"field": "is_credit", "op": "eq", "value": "1"}, cust)


def test_rule_risks_for_customer_filters_disabled():
    cust = {"note": "冻结"}
    rules = [
        {"name": "r1", "field": "note", "op": "contains", "value": "冻结", "level": "高", "risk_type": "财产冻结", "enabled": 1},
        {"name": "r2", "field": "note", "op": "contains", "value": "冻结", "level": "低", "risk_type": "其他", "enabled": 0},
    ]
    hits = hub.rule_risks_for_customer(cust, rules)
    assert len(hits) == 1 and hits[0]["level"] == "高" and hits[0]["source"] == "规则引擎"


def test_sqlite_source_query(tmp_path):
    dbf = tmp_path / "ext.db"
    conn = sqlite3.connect(dbf)
    conn.execute("CREATE TABLE t(name TEXT, ctype TEXT)")
    conn.execute("INSERT INTO t VALUES('测试公司甲','公司')")
    conn.commit(); conn.close()
    assert hub.test_source("sqlite", {"path": str(dbf)}) == "连接成功"
    r = hub.run_query("sqlite", {"path": str(dbf)}, "SELECT * FROM t")
    assert r["columns"] == ["name", "ctype"] and r["rows"] == [["测试公司甲", "公司"]]


def test_unsupported_type_raises():
    try:
        hub.test_source("oracle", {})
        raised = False
    except ValueError as e:
        raised = "不支持" in str(e)
    assert raised
