"""数据源抽象层：本期 LLM+博查 RAG；MCP（企查查/天眼查）为预留接口。"""
from ai_client import assess_customer
from logic import ScanError
from search import QUERY_TMPL, bocha_search


class LLMRagSource:
    """默认数据源：博查联网检索（可选）+ DeepSeek 归纳，RAG 模式。"""

    name = "llm"

    def assess(self, customer: dict, settings: dict) -> dict:
        if not settings.get("ai_api_key"):
            raise ScanError("未配置 AI API Key，请先在系统配置中填写")
        searched = False
        search_results = []
        search_note = ""
        if settings.get("search_enabled") == "1" and settings.get("search_api_key"):
            try:
                search_results = bocha_search(
                    settings["search_api_key"], QUERY_TMPL.format(name=customer["name"])
                )
                searched = True
            except Exception as e:
                search_note = f"联网搜索失败，已降级为纯模型知识（{e}）"
        result = assess_customer(settings, customer, search_results, searched)
        if search_note:
            result["search_note"] = search_note
            result["mode"] = f"{result['mode']}；{search_note}"
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
