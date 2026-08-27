"""Entity Resolver：新闻文本 → 关联股票（多对多）
组合：Ticker 词典 + 公司别名 + 正则匹配（LLM 确认可放入 analyzer 阶段）
"""
import re

COMPANIES = {
    "AAPL": "Apple Inc.", "NVDA": "NVIDIA Corp.", "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc.", "AMZN": "Amazon.com Inc.", "META": "Meta Platforms Inc.",
    "TSLA": "Tesla Inc.", "AMD": "Advanced Micro Devices Inc.", "ORCL": "Oracle Corp.",
    "MRVL": "Marvell Technology Inc.", "TSM": "Taiwan Semiconductor (TSMC)",
    "INTC": "Intel Corp.", "QCOM": "Qualcomm Inc.", "AVGO": "Broadcom Inc.",
    "MU": "Micron Technology Inc.", "SMCI": "Super Micro Computer Inc.",
    "ARM": "Arm Holdings", "NFLX": "Netflix Inc.", "PLTR": "Palantir Technologies",
    "CRM": "Salesforce Inc.", "UBER": "Uber Technologies", "COIN": "Coinbase Global",
    "SNOW": "Snowflake Inc.", "BA": "Boeing Co.", "JPM": "JPMorgan Chase",
    "GS": "Goldman Sachs", "DIS": "Walt Disney Co.", "NKE": "Nike Inc.",
    "WMT": "Walmart Inc.", "MCD": "McDonald's Corp.", "KO": "Coca-Cola Co.",
    "PEP": "PepsiCo Inc.", "CSCO": "Cisco Systems", "IBM": "IBM Corp.",
    "V": "Visa Inc.", "MA": "Mastercard Inc.", "HD": "Home Depot",
    "SBUX": "Starbucks Corp.", "XOM": "Exxon Mobil",
}

# 别名表（小写，len>=3 才会参与词边界匹配；短词用专属写法避免误匹配）
ALIASES = {
    "AAPL": ["apple inc", "apple's", "apple"],
    "NVDA": ["nvidia"],
    "MSFT": ["microsoft"],
    "GOOGL": ["alphabet", "google"],
    "AMZN": ["amazon"],
    "META": ["meta platforms", "facebook"],
    "TSLA": ["tesla"],
    "AMD": ["advanced micro devices"],
    "ORCL": ["oracle"],
    "MRVL": ["marvell"],
    "TSM": ["tsmc", "taiwan semiconductor"],
    "INTC": ["intel"],
    "QCOM": ["qualcomm"],
    "AVGO": ["broadcom"],
    "MU": ["micron"],
    "SMCI": ["super micro", "supermicro"],
    "ARM": ["arm holdings", "arm's"],
    "NFLX": ["netflix"],
    "PLTR": ["palantir"],
    "CRM": ["salesforce"],
    "UBER": ["uber"],
    "COIN": ["coinbase"],
    "SNOW": ["snowflake"],
    "BA": ["boeing"],
    "JPM": ["jpmorgan", "jp morgan"],
    "GS": ["goldman sachs"],
    "DIS": ["walt disney", "disney"],
    "NKE": ["nike"],
    "WMT": ["walmart"],
    "MCD": ["mcdonald"],
    "KO": ["coca-cola"],
    "PEP": ["pepsico", "pepsi"],
    "CSCO": ["cisco"],
    "IBM": ["international business machines", "ibm's"],
    "V": ["visa"],
    "MA": ["mastercard"],
    "HD": ["home depot"],
    "SBUX": ["starbucks"],
    "XOM": ["exxon"],
}

_SYMBOL_RE = {s: re.compile(r"\b" + s + r"\b") for s in COMPANIES}


def _mention_count(text, symbol, aliases):
    low = text.lower()
    count = 0
    for a in aliases:
        if len(a) >= 3:
            count += len(re.findall(r"\b" + re.escape(a) + r"\b", low))
    # 大写 Ticker 直接匹配（标题里常见 "NVDA"）
    count += len(_SYMBOL_RE[symbol].findall(text))
    return count


def resolve(item, primary_symbol=None):
    """返回 [{symbol, company_name, mention_count, relevance_score, is_primary}]，按主关联优先排序"""
    text = " ".join([item.title or "", item.summary or "", item.content or ""])
    found = {}
    for symbol, aliases in ALIASES.items():
        count = _mention_count(text, symbol, aliases)
        if count:
            found[symbol] = count
    if primary_symbol and primary_symbol not in found:
        found[primary_symbol] = 1
    if not found:
        return []

    result = []
    for symbol, count in found.items():
        relevance = round(min(1.0, 0.5 + 0.15 * count), 4)
        if symbol == primary_symbol:
            relevance = max(relevance, 0.9)
        result.append({
            "symbol": symbol,
            "company_name": COMPANIES.get(symbol),
            "mention_count": count,
            "relevance_score": relevance,
            "is_primary": 1 if symbol == primary_symbol else 0,
        })
    result.sort(key=lambda r: (-r["is_primary"], -r["mention_count"]))
    return result
