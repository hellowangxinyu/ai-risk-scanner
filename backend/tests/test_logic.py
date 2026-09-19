"""should_catch_up / is_due / extract_json / 导入校验 纯函数单测。"""
from datetime import date, datetime

import pytest

from logic import (
    extract_json,
    is_due,
    max_level,
    should_catch_up,
    validate_import_row,
)

CYCLES = {"高": 3, "中": 7, "低": 30, "无": 30}


# ---------- 宕机补跑判定 ----------

def test_catch_up_first_run_after_configured_time():
    assert should_catch_up("", datetime(2026, 9, 19, 3, 0), "02:00") is True


def test_catch_up_ran_today():
    assert should_catch_up("2026-09-19", datetime(2026, 9, 19, 3, 0), "02:00") is False


def test_catch_up_ran_yesterday_past_time():
    assert should_catch_up("2026-09-18", datetime(2026, 9, 19, 3, 0), "02:00") is True


def test_catch_up_before_configured_time():
    assert should_catch_up("2026-09-18", datetime(2026, 9, 19, 1, 0), "02:00") is False


def test_catch_up_exactly_at_configured_time():
    assert should_catch_up("2026-09-18", datetime(2026, 9, 19, 2, 0), "02:00") is True


def test_catch_up_invalid_configured_time_uses_default():
    assert should_catch_up("", datetime(2026, 9, 19, 3, 0), "bad") is True
    assert should_catch_up("", datetime(2026, 9, 19, 1, 0), "bad") is False


def test_catch_up_invalid_last_date_treated_as_never():
    assert should_catch_up("not-a-date", datetime(2026, 9, 19, 3, 0), "02:00") is True


# ---------- 到期判定 ----------

def test_due_never_scanned():
    assert is_due("", "", date(2026, 9, 19), CYCLES) is True


def test_due_not_due_high_recent():
    # 高风险档 3 天，2 天前扫的 → 未到期
    assert is_due("2026-09-17", "高", date(2026, 9, 19), CYCLES) is False


def test_due_high_after_3_days():
    assert is_due("2026-09-16", "高", date(2026, 9, 19), CYCLES) is True


def test_due_mid_7_days():
    assert is_due("2026-09-13", "中", date(2026, 9, 19), CYCLES) is False
    assert is_due("2026-09-12", "中", date(2026, 9, 19), CYCLES) is True


def test_due_none_30_days():
    assert is_due("2026-08-25", "无", date(2026, 9, 19), CYCLES) is False
    assert is_due("2026-08-20", "无", date(2026, 9, 19), CYCLES) is True


def test_due_corrupt_last_scan_at_treated_as_due():
    assert is_due("garbage", "高", date(2026, 9, 19), CYCLES) is True


# ---------- 风险等级 ----------

def test_max_level():
    assert max_level([]) == ""
    assert max_level(["低", "高", "中"]) == "高"
    assert max_level(["低", "中"]) == "中"
    assert max_level(["未知"]) == ""


# ---------- JSON 容错：首 { 至末 } 截取 ----------

def test_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_fenced():
    text = '```json\n{"has_risk": true, "risks": []}\n```'
    assert extract_json(text) == {"has_risk": True, "risks": []}


def test_json_with_surrounding_text():
    text = '好的，以下是评估结果：\n{"a": {"b": 2}}\n以上。'
    assert extract_json(text) == {"a": {"b": 2}}


def test_json_nested_braces_first_to_last():
    text = '{"a": "包含 } 花括号的字符串", "b": {"c": [1, 2]}}'
    assert extract_json(text)["b"] == {"c": [1, 2]}


def test_json_no_object_raises():
    with pytest.raises(ValueError):
        extract_json("没有任何 JSON")


def test_json_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


def test_json_non_object_raises():
    with pytest.raises(ValueError):
        extract_json("[1, 2, 3]")


# ---------- 导入行校验 ----------

def test_import_ok_company():
    ok, fields, reason = validate_import_row("某某建材有限公司 ", "公司", "91xxx", "张三", "")
    assert ok and fields["name"] == "某某建材有限公司" and reason == ""


def test_import_empty_type_defaults_company():
    ok, fields, _ = validate_import_row("某某", "", "", "", "")
    assert ok and fields["ctype"] == "公司"


def test_import_empty_name_fails():
    ok, _, reason = validate_import_row("  ", "公司", "", "", "")
    assert not ok and "名称为空" in reason


def test_import_bad_type_fails():
    ok, _, reason = validate_import_row("某某", "企业", "", "", "")
    assert not ok and "类型非法" in reason


def test_import_personal_ok():
    ok, fields, _ = validate_import_row("李四", "个人", "", "", "")
    assert ok and fields["ctype"] == "个人"
