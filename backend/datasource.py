"""数据源抽象层：本期 LLM+联网检索（DeepSeek 原生搜索 / 博查）；MCP 为预留接口。"""
from ai_client import assess_customer
from logic import ScanError
from search import QUERY_TMPL, bocha_search, deepseek_search


def _run_search(settings: dict, query: str):
    """按配置的搜索提供方执行检索。

    返回 (results, searched, search_paid, usage_in, usage_out, provider_label)。
    search_paid 表示该次搜索是否按"次"单独计费（博查）；DeepSeek 原生搜索
    的成本体现为模型 Token，由 usage_in/out 计入费用。
    """
    provider = settings.get("search_provider") or "deepseek"
    if provider == "bocha":
        results = bocha_search(settings["search_api_key"], query)
        return results, True, True, 0, 0, "博查搜索"
    results, tin, tout = deepseek_search(settings["ai_api_key"], query)
    return results, True, False, tin, tout, "DeepSeek 原生搜索"


class LLMRagSource:
    """默认数据源：联网检索（DeepSeek 原生搜索或博查）+ DeepSeek 归纳，RAG 模式。"""

    name = "llm"

    def assess(self, customer: dict, settings: dict) -> dict:
        if not settings.get("ai_api_key"):
            raise ScanError("未配置 AI API Key，请先在系统配置中填写")
        searched = False
        search_paid = False
        search_results = []
        search_note = ""
        usage_extra = (0, 0)
        provider_label = ""
        if settings.get("search_enabled") == "1":
            try:
                search_results, searched, search_paid, tin, tout, provider_label = _run_search(
                    settings, QUERY_TMPL.format(name=customer["name"])
                )
                usage_extra = (tin, tout)
            except Exception as e:
                search_note = f"联网搜索失败，已降级为纯模型知识（{e}）"
        result = assess_customer(settings, customer, search_results, searched,
                                 usage_extra=usage_extra, search_label=provider_label)
        if search_note:
            result["search_note"] = search_note
            result["mode"] = f"{result['mode']}；{search_note}"
        result["search_paid"] = search_paid
        return result


class McpSource:
    """预留：企查查/天眼查 MCP 权威数据源，购买 API 套餐后在此适配。"""

    name = "mcp"

    def assess(self, customer: dict, settings: dict) -> dict:
        raise ScanError(
            "MCP 数据源为预留接口：待购买企查查/天眼查 API 套餐后适配，当前请使用 LLM 数据源"
        )


REGISTRY = {"llm": LLMRagSource(), "mcp": McpSource()}


def get_source(settings: dict):
    key = settings.get("datasource") or "llm"
    return REGISTRY.get(key) or REGISTRY["llm"]
