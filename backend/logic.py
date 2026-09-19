"""纯业务逻辑（无 IO 依赖），便于单元测试。"""
from datetime import date, datetime, time as dtime

# 风险等级 → 扫描间隔天数的档位 key
LEVEL_KEYS = ("高", "中", "低")
LEVEL_RANK = {"高": 0, "中": 1, "低": 2}
VALID_IMPORT_TYPES = {"公司", "个人"}


class ScanError(Exception):
    """单客户扫描失败（网络/配置/解析等），会被记录到批次明细。"""


def parse_hhmm(s: str, default: str = "02:00") -> dtime:
    try:
        h, m = str(s).split(":")
        return dtime(int(h), int(m))
    except Exception:
        return parse_hhmm(default)


def should_catch_up(last_run_date: str, now: datetime, configured_time: str) -> bool:
    """自动扫描宕机补跑判定（纯函数）。

    今天尚未跑过 且 当前时间已过设定时刻 → 需要补跑。
    """
    if last_run_date:
        try:
            if datetime.strptime(last_run_date, "%Y-%m-%d").date() >= now.date():
                return False
        except ValueError:
            pass  # 日期损坏视为从未跑过
    return now.time() >= parse_hhmm(configured_time)


def level_interval(level: str, cycles: dict) -> int:
    """按风险等级取扫描间隔天数，未知等级按'无'档处理。"""
    days = cycles.get(level)
    if not days or int(days) <= 0:
        days = cycles.get("无", 30)
    return max(int(days), 1)


def is_due(last_scan_at: str, today: date, cycles: dict, is_credit: bool = False) -> bool:
    """客户扫描到期判定（纯函数）。

    客户风险等级由授信状态唯一决定：授信=高（高风险档间隔），非授信=低（低风险档间隔）。
    从未扫描一律视为到期。
    """
    if not last_scan_at:
        return True
    try:
        last = datetime.fromisoformat(str(last_scan_at)).date()
    except ValueError:
        return True
    tier = "高" if is_credit else "低"
    days = level_interval(tier, cycles)
    return (today - last).days >= days


def parse_credit_flag(value) -> bool:
    """解析授信标识：是/1/y/yes/true → True；否/0/n/no/false/空 → False；其他抛 ValueError。"""
    v = str(value or "").strip().lower()
    if v in ("是", "1", "y", "yes", "true"):
        return True
    if v in ("否", "0", "n", "no", "false", ""):
        return False
    raise ValueError("授信标识非法（应为 是/否）")


def normalize_risk_title(title: str) -> str:
    """风险标题归一化：去空白、转小写，用于跨批次匹配同一风险项。"""
    import re as _re

    return _re.sub(r"\s+", "", str(title or "")).lower()


def compute_lifecycle(records: list, latest_valid_batch: dict) -> list:
    """跨批次聚合同一风险项，生成"风险项生命周期"清单（纯函数）。

    records：风险记录 dict 列表（需含 batch_id, scan_date, customer_id, customer_name,
             risk_type, level, title, description）；
    latest_valid_batch：{("id", customer_id): batch_id}，每客户最近一次有效扫描
             （有风险/无风险）的批次；客户无有效扫描记录时不出现在字典中。

    匹配规则：同一客户 + 同一风险类型 + 标题归一化一致 → 同一风险项。
    返回聚合项列表（活跃在前、等级高在前）：
    {customer_id, customer_name, risk_type, level, title, description,
     first_seen, last_seen, batch_count, status(活跃/已消失)}
    status：客户最近一次有效扫描批次中仍包含该风险 → 活跃；未包含 → 已消失；
    客户尚无有效扫描（如最近一次扫描失败）→ 维持活跃。
    """
    groups = {}
    for r in records:
        cid = r.get("customer_id")
        ck = ("id", cid) if cid is not None else ("name", r.get("customer_name"))
        key = (ck, r.get("risk_type"), normalize_risk_title(r.get("title")))
        g = groups.setdefault(key, {
            "customer_id": cid,
            "customer_name": r.get("customer_name"),
            "risk_type": r.get("risk_type"),
            "title": r.get("title"),
            "description": r.get("description"),
            "level": r.get("level"),
            "first_seen": r.get("scan_date"),
            "last_seen": r.get("scan_date"),
            "batch_count": 0,
            "batches": set(),
            "latest_bid": -1,
        })
        sd = r.get("scan_date") or ""
        if sd and (not g["first_seen"] or sd < g["first_seen"]):
            g["first_seen"] = sd
        if sd and (not g["last_seen"] or sd > g["last_seen"]):
            g["last_seen"] = sd
        g["batch_count"] += 1
        if r.get("batch_id") is not None:
            g["batches"].add(r["batch_id"])
            if r["batch_id"] > g["latest_bid"]:
                g["latest_bid"] = r["batch_id"]
                g["level"] = r.get("level")
                g["title"] = r.get("title")
                g["description"] = r.get("description")
    items = []
    for g in groups.values():
        cid = g["customer_id"]
        ck = ("id", cid) if cid is not None else ("name", g["customer_name"])
        cur = latest_valid_batch.get(ck)
        status = "活跃" if (cur is None or cur in g["batches"]) else "已消失"
        items.append({
            "customer_id": cid,
            "customer_name": g["customer_name"],
            "risk_type": g["risk_type"],
            "level": g["level"],
            "title": g["title"],
            "description": g["description"],
            "first_seen": g["first_seen"],
            "last_seen": g["last_seen"],
            "batch_count": g["batch_count"],
            "status": status,
        })
    items.sort(key=lambda x: (
        0 if x["status"] == "活跃" else 1,
        LEVEL_RANK.get(x["level"], 9),
        x["customer_name"],
        x["title"],
    ))
    return items


def max_level(levels) -> str:
    """取最高风险等级，空列表返回 ''。"""
    best, best_rank = "", 99
    for lv in levels:
        rank = LEVEL_RANK.get(lv)
        if rank is not None and rank < best_rank:
            best, best_rank = lv, rank
    return best


def validate_import_row(name: str, ctype: str, credit_code: str, contact: str, note: str):
    """校验一条导入记录，返回 (ok, 清洗后的字段 dict, 失败原因)。"""
    name = str(name or "").strip()
    if not name:
        return False, None, "名称为空"
    if len(name) > 200:
        return False, None, "名称过长（>200 字符）"
    ctype = str(ctype or "").strip()
    if not ctype:
        ctype = "公司"
    if ctype not in VALID_IMPORT_TYPES:
        return False, None, f"类型非法：{ctype}（只允许 公司/个人）"
    row = {
        "name": name,
        "ctype": ctype,
        "credit_code": str(credit_code or "").strip(),
        "contact": str(contact or "").strip(),
        "note": str(note or "").strip(),
    }
    return True, row, ""


def extract_json(text: str) -> dict:
    """从模型返回文本中解析 JSON 对象。

    DeepSeek 返回体为单个顶层对象（内部可嵌套），剥掉 ```json 围栏后
    按"首 { 至末 }"截取 + json.loads，比逐字符找首个完整对象更稳、语义等价。
    """
    if text is None:
        raise ValueError("模型返回为空")
    t = str(text).strip()
    if "```" in t:
        out_lines = []
        in_fence = False
        for line in t.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            out_lines.append(line)
        t = "\n".join(out_lines).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("返回内容中未找到 JSON 对象")
    import json

    obj = json.loads(t[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("返回的 JSON 不是对象")
    return obj
