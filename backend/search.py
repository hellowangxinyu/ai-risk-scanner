"""博查 Web Search 适配（RAG 检索源）。失败由上层降级处理。"""
import httpx

BOCHA_URL = "https://api.bochaai.com/v1/web-search"
# 每客户 1 次查询（1 次 = 1 次计费）
QUERY_TMPL = "{name} 诉讼 OR 行政处罚 OR 经营异常 OR 失信 OR 被执行人"
COUNT = 8


def bocha_search(api_key: str, query: str, count: int = COUNT, timeout: float = 20.0):
    """返回 [{title, url, summary}]；失败抛异常，由上层降级为纯模型知识。"""
    r = httpx.post(
        BOCHA_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "count": count, "summary": True},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    web = ((body.get("data") or {}).get("webPages") or {})
    out = []
    for v in (web.get("value") or []):
        out.append(
            {
                "title": str(v.get("name") or "").strip(),
                "url": str(v.get("url") or "").strip(),
                "summary": str(v.get("summary") or v.get("snippet") or "").strip(),
            }
        )
    return out


def build_search_block(results) -> str:
    """把检索结果拼成注入提示词的文本块，逐条 [标题] 摘要(URL)。"""
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        summary = r.get("summary") or ""
        if len(summary) > 300:
            summary = summary[:300] + "…"
        lines.append(f"{i}. [{r.get('title') or '无标题'}] {summary} ({r.get('url')})")
    return "\n".join(lines)
