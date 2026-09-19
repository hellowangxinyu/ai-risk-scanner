"""联网搜索适配层：DeepSeek 原生搜索（默认，复用 AI Key）+ 博查 Web Search（备选）。"""
import httpx

BOCHA_URL = "https://api.bochaai.com/v1/web-search"
# 每客户 1 次查询（博查按次计费）
QUERY_TMPL = "{name} 诉讼 OR 行政处罚 OR 经营异常 OR 失信 OR 被执行人"
COUNT = 8

# DeepSeek 原生搜索：Anthropic 兼容 Messages 端点 + web_search_20250305 服务端工具。
# 一次搜索消耗一个完整模型轮次（token 计费），复用 AI API Key。
DS_SEARCH_BASE = "https://api.deepseek.com/anthropic/v1"
DS_SEARCH_MODEL = "deepseek-v4-flash"
DS_SEARCH_MAX_USES = 5


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


def deepseek_search(api_key: str, query: str, base_url: str = DS_SEARCH_BASE,
                    model: str = DS_SEARCH_MODEL, max_uses: int = DS_SEARCH_MAX_USES,
                    timeout: float = 90.0):
    """DeepSeek 原生联网搜索（Anthropic 兼容 Messages + web_search 服务端工具）。

    返回 (sources, input_tokens, output_tokens)，sources 为 [{title, url, summary}]；
    summary 取自响应 text 块 citations 的 cited_text（按 URL 关联，可能为空）。
    失败抛异常，由上层降级为纯模型知识。
    """
    url = base_url.rstrip("/") + "/messages"
    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": f"Perform a web search for the query: {query}"}],
        }],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
    }
    r = httpx.post(
        url,
        headers={
            "x-api-key": api_key,
            "authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    r.raise_for_status()
    payload = r.json()
    blocks = payload.get("content") or []
    result_blocks = [b for b in blocks if b.get("type") == "web_search_tool_result"]
    if not result_blocks:
        raise RuntimeError("响应中无 web_search_tool_result 块（搜索可能未触发）")
    # URL -> 引文摘要（snippet 源）
    snippets = {}
    for b in blocks:
        if b.get("type") != "text":
            continue
        for cite in (b.get("citations") or []):
            u, t = cite.get("url"), cite.get("cited_text")
            if u and t and u not in snippets:
                snippets[u] = t
    out, seen = [], set()
    for rb in result_blocks:
        for item in (rb.get("content") or []):
            if item.get("type") != "web_search_result":
                continue
            u = item.get("url") or ""
            if not u or u in seen:
                continue
            seen.add(u)
            out.append({
                "title": str(item.get("title") or "").strip(),
                "url": u,
                "summary": snippets.get(u, ""),
            })
    usage = payload.get("usage") or {}
    return out, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)


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
