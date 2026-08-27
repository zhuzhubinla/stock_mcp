"""事件类型识别（关键词规则；LLM 分析结果可覆盖）"""
EVENT_KEYWORDS = {
    "earnings": ["earnings", "quarterly results", "fiscal", "profit report", "eps"],
    "guidance": ["guidance", "forecast", "outlook"],
    "revenue": ["revenue", "sales growth", "top line"],
    "profit": ["profit", "net income", "margin"],
    "product_launch": ["launch", "unveil", "introduce", "release", "debut", "new product"],
    "product_delay": ["delay", "postpone", "push back", "slip"],
    "product_failure": ["recall", "defect", "glitch", "outage", "fault", "malfunction"],
    "m_and_a": ["acquisition", "merger", "acquire", "takeover", "buyout", "to acquire"],
    "partnership": ["partnership", "collaborat", "alliance", "joint venture", "teams up"],
    "contract": ["contract", "agreement", "awarded", "deal worth"],
    "customer": ["customer", "orders", "order backlog"],
    "supplier": ["supplier", "supply chain", "component maker"],
    "regulation": ["regulation", "regulatory", "antitrust", "fcc", "ftc", "sec", "compliance", "probe"],
    "lawsuit": ["lawsuit", "sue", "sues", "sued", "litigation", "court ruling"],
    "government": ["government", "tariff", "export control", "sanction", "policy"],
    "management": ["ceo", "cfo", "executive", "appoints", "resign", "stepping down", "chief"],
    "analyst_upgrade": ["upgrade", "buy rating", "overweight", "raise price target", "bullish"],
    "analyst_downgrade": ["downgrade", "sell rating", "underweight", "cut price target", "bearish"],
    "insider_buy": ["insider buying", "insider purchased", "shares bought"],
    "insider_sell": ["insider selling", "insider sold", "shares sold"],
    "financing": ["offering", "ipo", "secondary offering", "fundraise", "funding round", "raise capital"],
    "buyback": ["buyback", "repurchase"],
    "dividend": ["dividend", "payout"],
    "macro": ["fed", "federal reserve", "inflation", "interest rate", "rate cut", "rate hike", "cpi", "gdp", "recession", "jobs report"],
    "cyber_attack": ["cyber", "hack", "breach", "ransomware", "data breach"],
    "recall": ["recall"],
    "bankruptcy": ["bankruptcy", "chapter 11", "insolvent", "default"],
}

# 规则引擎的默认影响分（0-1）：事件类型 → 对股价潜在影响
IMPACT_BY_EVENT = {
    "earnings": 0.80, "guidance": 0.70, "revenue": 0.60, "profit": 0.55,
    "product_launch": 0.45, "product_delay": 0.55, "product_failure": 0.80,
    "m_and_a": 0.75, "partnership": 0.40, "contract": 0.55, "customer": 0.60, "supplier": 0.35,
    "regulation": 0.70, "lawsuit": 0.60, "government": 0.65,
    "management": 0.55, "analyst_upgrade": 0.30, "analyst_downgrade": 0.35,
    "insider_buy": 0.30, "insider_sell": 0.35,
    "financing": 0.40, "buyback": 0.45, "dividend": 0.35,
    "macro": 0.60, "cyber_attack": 0.75, "recall": 0.75, "bankruptcy": 0.90,
    "other": 0.20,
}

TIME_HORIZON_BY_EVENT = {
    "earnings": "1-5d", "guidance": "1-5d", "analyst_upgrade": "1-5d", "analyst_downgrade": "1-5d",
    "product_failure": "1-5d", "bankruptcy": "1-5d", "cyber_attack": "1-5d", "recall": "1-5d",
    "m_and_a": "5-30d", "regulation": "5-30d", "lawsuit": "5-30d", "government": "5-30d",
    "macro": "5-30d", "management": "5-30d", "insider_buy": "5-30d", "insider_sell": "5-30d",
    "product_launch": "5-30d", "contract": "5-30d", "customer": "5-30d", "supplier": "5-30d",
    "partnership": "5-30d", "financing": "5-30d", "buyback": "5-30d", "dividend": "5-30d",
    "other": "1-5d",
}


def extract(item):
    """返回 (event_type, matched_keywords)"""
    text = f"{item.title or ''} {item.summary or ''}".lower()
    hits = {}
    for event_type, keywords in EVENT_KEYWORDS.items():
        matched = [k for k in keywords if k in text]
        if matched:
            hits[event_type] = matched
    if not hits:
        return "other", []
    # 命中关键词多者胜；平局按预置影响分高者胜
    best = max(hits, key=lambda et: (len(hits[et]), IMPACT_BY_EVENT.get(et, 0)))
    return best, hits[best]
