"""DeepSeek（OpenAI 兼容）客户端：response_format 优先 + 自动回退，JSON 容错，失败重试一次。"""
import re

import httpx

from logic import ScanError, extract_json

RISK_TYPES = ["工商", "诉讼", "财产冻结", "股东变更", "股权质押", "经营", "财务", "其他"]
LEVELS = ["高", "中", "低"]
TIMEOUT = 120.0

SYSTEM_PROMPT = (
    "你是资深企业财务风控分析师。基于所给资料审慎评估客户风险，绝不虚构事实；"
    "资料或知识不足以确认时，宁可标记为无风险。只输出一个 JSON 对象，不要输出任何其他文字。"
)

USER_PROMPT_TMPL = """请评估以下客户当前的风险信息。

客户名称：{name}
客户类型：{ctype}
统一社会信用代码：{credit_code}
{search_section}
评估维度：工商、诉讼、财产冻结、股东变更、股权质押、经营、财务等。

要求：
1. 有明确依据才列为风险，不得编造；资料与你的知识都不足以判断时，不列为风险。
2. risk_type 取值只能是：工商/诉讼/财产冻结/股东变更/股权质押/经营/财务/其他。
3. level 取值：高/中/低。
4. risk_date 为风险发生或披露日期，格式 YYYY-MM-DD，不确定则留空字符串。
5. source 为信息来源简述；没有联网检索资料时写"模型知识，仅供参考"。

只输出如下结构的 JSON：
{{"has_risk": true, "summary": "一句话总结", "risks": [{{"risk_type": "诉讼", "level": "高", "title": "风险标题", "description": "风险描述", "risk_date": "2025-01-01", "source": "来源"}}]}}"""


def build_messages(customer: dict, search_results: list, searched: bool):
    if searched and search_results:
        from search import build_search_block

        search_section = (
            "以下是联网检索到的公开资料（可能不完整，仅供参考）：\n"
            + build_search_block(search_results)
            + "\n"
        )
    else:
        search_section = ""
    user = USER_PROMPT_TMPL.format(
        name=customer["name"],
        ctype=customer.get("ctype", "公司"),
        credit_code=customer.get("credit_code") or "未提供",
        search_section=search_section,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _post_chat(settings: dict, messages, use_json_mode: bool, timeout: float = TIMEOUT):
    base = (settings.get("ai_base_url") or "").rstrip("/")
    if not base:
        raise ScanError("未配置 AI Base URL")
    key = settings.get("ai_api_key") or ""
    if not key:
        raise ScanError("未配置 AI API Key")
    payload = {
        "model": settings.get("ai_model") or "deepseek-chat",
        "messages": messages,
        "temperature": 0.2,
    }
    if use_json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = httpx.post(
        base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code == 400 and use_json_mode:
        # 服务端不支持 response_format，去掉后重发
        r = _post_chat(settings, messages, use_json_mode=False, timeout=timeout)
    return r


def normalize_assessment(parsed: dict, model: str, searched: bool, search_label: str = "") -> dict:
    risks = []
    for item in (parsed.get("risks") or []):
        if not isinstance(item, dict):
            continue
        risk_type = str(item.get("risk_type") or "").strip()
        if risk_type not in RISK_TYPES:
            risk_type = "其他"
        level = str(item.get("level") or "").strip()
        if level not in LEVELS:
            level = "低"
        risk_date = str(item.get("risk_date") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", risk_date):
            risk_date = ""
        risks.append(
            {
                "risk_type": risk_type,
                "level": level,
                "title": str(item.get("title") or "").strip() or f"{risk_type}风险",
                "description": str(item.get("description") or "").strip(),
                "risk_date": risk_date,
                "source": str(item.get("source") or "").strip(),
            }
        )
    label = search_label or "联网搜索"
    mode = (
        f"AI 检索（{label} + 大模型分析，仅供参考）"
        if searched
        else f"AI 分析（{model} 知识，仅供参考）"
    )
    return {
        "has_risk": bool(risks),
        "summary": str(parsed.get("summary") or "").strip(),
        "risks": risks,
        "mode": mode,
    }


def assess_customer(settings: dict, customer: dict, search_results: list, searched: bool,
                    usage_extra: tuple = (0, 0), search_label: str = "") -> dict:
    """调大模型评估单个客户。失败（网络/HTTP/解析）整体重试一次，仍失败抛 ScanError。

    usage_extra：联网搜索轮次消耗的 Token（DeepSeek 原生搜索按模型轮次计费），
    会并入该客户的 Token 统计与费用估算。
    """
    messages = build_messages(customer, search_results, searched)
    model = settings.get("ai_model") or "deepseek-chat"
    label = search_label or "联网搜索"
    last_err = None
    for attempt in range(2):
        try:
            r = _post_chat(settings, messages, use_json_mode=True)
            if r.status_code != 200:
                raise ScanError(f"AI 接口返回 {r.status_code}：{r.text[:200]}")
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            parsed = extract_json(content)
            result = normalize_assessment(parsed, model, searched, label)
            result["tokens_in"] = int(usage.get("prompt_tokens") or 0) + int(usage_extra[0])
            result["tokens_out"] = int(usage.get("completion_tokens") or 0) + int(usage_extra[1])
            result["searched"] = searched
            result["outcome"] = "有风险" if result["has_risk"] else "无风险"
            return result
        except ScanError as e:
            if "未配置" in str(e):
                raise  # 配置类错误重试无意义
            last_err = e
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            last_err = e
    raise ScanError(f"AI 调用失败（已重试）：{last_err}")


def ping(settings: dict) -> tuple:
    """测试连通性，返回 (ok, message)。"""
    base = (settings.get("ai_base_url") or "").rstrip("/")
    key = settings.get("ai_api_key") or ""
    model = settings.get("ai_model") or "deepseek-chat"
    if not base or not key:
        return False, "请先填写 Base URL 和 API Key"
    try:
        r = httpx.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "请只回复两个字：正常"}],
                "max_tokens": 16,
            },
            timeout=20,
        )
        if r.status_code != 200:
            return False, f"接口返回 {r.status_code}：{r.text[:200]}"
        content = r.json()["choices"][0]["message"]["content"]
        return True, f"连接正常，模型 {model} 回复：{content.strip()[:50]}"
    except Exception as e:
        return False, f"连接失败：{e}"
