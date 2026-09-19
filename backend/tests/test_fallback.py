"""联网搜索失败降级 + AI 失败重试逻辑单测（mock，不发起真实网络请求）。"""
import ai_client
import datasource
import search as search_mod
from logic import ScanError


def test_search_failure_degrades(monkeypatch):
    """博查搜索抛异常 → 降级为纯模型知识，结果注明降级。"""
    def boom(api_key, query, **kw):
        raise RuntimeError("网络错误")

    monkeypatch.setattr(datasource, "bocha_search", boom)

    def fake_assess(settings, customer, search_results, searched, usage_extra=(0, 0), search_label=""):
        assert searched is False, "搜索失败后应以未联网模式调用 AI"
        assert search_results == []
        return {
            "outcome": "无风险", "summary": "ok", "risks": [],
            "tokens_in": 1, "tokens_out": 1, "searched": False, "mode": "m",
        }

    monkeypatch.setattr(datasource, "assess_customer", fake_assess)
    settings = {
        "search_enabled": "1", "search_provider": "bocha", "search_api_key": "k",
        "datasource": "llm", "ai_api_key": "ai-key",
    }
    res = datasource.get_source(settings).assess({"name": "测试客户"}, settings)
    assert res["searched"] is False
    assert res["search_paid"] is False
    assert "降级" in res["search_note"]


def test_deepseek_search_selected_and_usage_merged(monkeypatch):
    """DeepSeek 原生搜索：复用 AI Key，搜索轮次 Token 并入统计，不计按次搜索费。"""
    calls = {}

    def fake_ds_search(api_key, query, **kw):
        calls["api_key"] = api_key
        calls["query"] = query
        return [{"title": "t", "url": "u", "summary": "s"}], 1500, 800

    monkeypatch.setattr(datasource, "deepseek_search", fake_ds_search)

    def fake_assess(settings, customer, search_results, searched, usage_extra=(0, 0), search_label=""):
        assert searched is True
        assert search_results and search_results[0]["url"] == "u"
        assert usage_extra == (1500, 800), "搜索轮次 Token 应并入统计"
        assert "DeepSeek 原生搜索" in search_label
        return {
            "outcome": "有风险", "summary": "ok", "risks": [{"risk_type": "诉讼", "level": "高",
            "title": "t", "description": "d", "risk_date": "", "source": ""}],
            "tokens_in": 100 + usage_extra[0], "tokens_out": 50 + usage_extra[1],
            "searched": True, "mode": "m",
        }

    monkeypatch.setattr(datasource, "assess_customer", fake_assess)
    settings = {
        "search_enabled": "1", "search_provider": "deepseek", "datasource": "llm",
        "ai_api_key": "ai-key",
    }
    res = datasource.get_source(settings).assess({"name": "测试客户"}, settings)
    assert calls["api_key"] == "ai-key"
    assert calls["query"].startswith("测试客户")
    assert res["search_paid"] is False, "DeepSeek 原生搜索不应计入按次搜索费"


def test_deepseek_search_response_parsing(monkeypatch):
    """解析 Anthropic Messages 响应：web_search_tool_result 块 + citations 引文。"""
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "content": [
                    {"type": "web_search_tool_result", "content": [
                        {"type": "web_search_result", "url": "https://a.com", "title": "A公司被诉", "page_age": "2026-01-01"},
                        {"type": "web_search_result", "url": "https://b.com", "title": "B报道"},
                        {"type": "web_search_result", "url": "https://a.com", "title": "重复URL"},
                    ]},
                    {"type": "text", "text": "结论……", "citations": [
                        {"url": "https://a.com", "cited_text": "A公司因合同纠纷被起诉……"},
                    ]},
                ],
                "usage": {"input_tokens": 1200, "output_tokens": 600},
            }

    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: FakeResp())
    sources, tin, tout = search_mod.deepseek_search("key", "测试查询")
    assert len(sources) == 2, "应按 URL 去重"
    assert sources[0]["title"] == "A公司被诉"
    assert sources[0]["summary"] == "A公司因合同纠纷被起诉……"
    assert sources[1]["summary"] == ""
    assert (tin, tout) == (1200, 600)


def test_deepseek_search_no_result_block_raises(monkeypatch):
    """响应缺少 web_search_tool_result 块 → 报错（上层降级处理）。"""
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "普通回复，没有搜索"}]}

    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: FakeResp())
    try:
        search_mod.deepseek_search("key", "测试查询")
        raised = False
    except RuntimeError as e:
        raised = "web_search_tool_result" in str(e)
    assert raised


def test_missing_ai_key_fails_fast(monkeypatch):
    """未配置 AI Key：直接报错，不发起搜索（省搜索费）。"""
    called = {"search": False}

    def spy_search(api_key, query, **kw):
        called["search"] = True
        return []

    monkeypatch.setattr(datasource, "bocha_search", spy_search)
    settings = {"search_enabled": "1", "search_api_key": "k", "datasource": "llm", "ai_api_key": ""}
    try:
        datasource.get_source(settings).assess({"name": "测试客户"}, settings)
        raised = False
    except ScanError as e:
        raised = "API Key" in str(e)
    assert raised and called["search"] is False


def test_ai_http_400_falls_back_to_plain_mode(monkeypatch):
    """response_format 被服务端 400 拒绝 → _post_chat 内部自动去掉重发并成功解析。"""
    calls = []

    class FakeResp:
        status_code = 200

        def __init__(self, status, body):
            self.status_code = status
            self._body = body
            self.text = ""

        def json(self):
            return self._body

    ok_body = {
        "choices": [{"message": {"content": '{"has_risk": false, "summary": "无", "risks": []}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    def fake_post(url, headers=None, json=None, timeout=None):
        has_json_mode = "response_format" in (json or {})
        calls.append(has_json_mode)
        if has_json_mode:
            return FakeResp(400, {"error": "response_format unsupported"})
        return FakeResp(200, ok_body)

    monkeypatch.setattr(ai_client.httpx, "post", fake_post)
    settings = {"ai_base_url": "https://x/v1", "ai_api_key": "k", "ai_model": "m"}
    res = ai_client.assess_customer(settings, {"name": "某客户", "ctype": "公司"}, [], False)
    assert calls == [True, False]
    assert res["outcome"] == "无风险"
    assert res["tokens_in"] == 10


def test_ai_retries_once_then_raises(monkeypatch):
    """网络错误重试一次，仍失败抛 ScanError。"""
    attempts = {"n": 0}

    def fake_post(settings, messages, use_json_mode, timeout=1):
        attempts["n"] += 1
        raise ai_client.httpx.ConnectError("连接失败")

    monkeypatch.setattr(ai_client, "_post_chat", fake_post)
    settings = {"ai_base_url": "https://x/v1", "ai_api_key": "k", "ai_model": "m"}
    try:
        ai_client.assess_customer(settings, {"name": "某客户", "ctype": "公司"}, [], False)
        raised = False
    except ScanError as e:
        raised = "已重试" in str(e)
    assert raised and attempts["n"] == 2


def test_normalize_maps_unknown_type_and_level():
    res = ai_client.normalize_assessment(
        {"has_risk": True, "summary": "s", "risks": [
            {"risk_type": "不明维度", "level": "特大", "title": "", "description": "d", "risk_date": "2025/01/01", "source": ""}
        ]},
        "deepseek-chat", False,
    )
    r = res["risks"][0]
    assert r["risk_type"] == "其他"
    assert r["level"] == "低"
    assert r["title"] == "其他风险"
    assert r["risk_date"] == ""  # 非法日期清洗为空
    assert "仅供参考" in res["mode"]
