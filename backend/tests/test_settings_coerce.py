"""设置项服务端校验测试：非法值必须被拒绝，不能落库。"""
import pytest

from routers.settings import _coerce_value


def test_coerce_cycle_valid():
    assert _coerce_value("cycle_high", "3") == "3"
    assert _coerce_value("cycle_low", "30.0") == "30"


def test_coerce_cycle_rejects_garbage_and_range():
    with pytest.raises(ValueError):
        _coerce_value("cycle_low", "abc")
    with pytest.raises(ValueError):
        _coerce_value("cycle_high", "0")
    with pytest.raises(ValueError):
        _coerce_value("cycle_mid", "999")


def test_coerce_price():
    assert _coerce_value("price_in", "2") == "2.0"
    with pytest.raises(ValueError):
        _coerce_value("price_out", "-1")
    with pytest.raises(ValueError):
        _coerce_value("price_search", "abc")


def test_coerce_switches_and_enums():
    assert _coerce_value("search_enabled", "1") == "1"
    assert _coerce_value("search_enabled", "true") == "1"
    assert _coerce_value("search_enabled", "0") == "0"
    assert _coerce_value("search_provider", "deepseek") == "deepseek"
    with pytest.raises(ValueError):
        _coerce_value("search_provider", "baidu")
    with pytest.raises(ValueError):
        _coerce_value("datasource", "web")
    with pytest.raises(ValueError):
        _coerce_value("auto_scan_time", "25:00")
    assert _coerce_value("auto_scan_time", "02:00") == "02:00"


def test_coerce_org_fallback():
    assert _coerce_value("default_org", "  ") == "本公司"
    assert _coerce_value("default_org", " 亚泰 ") == "亚泰"
