"""Prediction → Stock Mapping（设计文档 8.6 节）

预测事件本身不是股票信号，必须经 Knowledge Graph 完成实体/产业链映射后
才能进入 Stock Score。例如：
  AI CapEx ↑ → Data Center → GPU → NVDA/AMD/HBM → MU/TSMC/MRVL

映射规则（关键词 → 行业/公司）：
  1. 事件标题/类别关键词 → 命中行业（industry 表 code/name）
  2. 行业 → 暴露公司（industry_company 表 exposure_weight）
  3. 产业链传播：行业 → 链上节点 → 上下游行业 → 公司（industry_chain_* + company_relationship）
  4. 生成 prediction_signal（entity_type=stock/industry, propagation_path 记录路径）
"""
import sys
import json
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn
from data.repositories import prediction_repo as repo
from domain.prediction.engine import (compute_consensus, confidence_from_consensus,
                                      direction_from_probability)

# 事件关键词 → (industry_code, 映射描述)
KEYWORD_MAP = [
    # AI / 半导体
    (["ai capex", "data center", "datacenter", "ai spending", "nvidia", "gpu",
      "chips", "semiconductor", "hbm", "foundry", "openai", "chatgpt"],
     "ai_chip", "AI CapEx → Data Center → GPU"),
    (["memory", "dram", "nand", "hbm"], "memory", "AI CapEx → HBM/DRAM"),
    (["tsmc", "foundry", "wafer"], "foundry", "AI CapEx → Foundry"),
    (["marvell", "network chip", "interconnect"], "network", "AI CapEx → Network Chip"),
    (["cloud", "azure", "aws", "oracle cloud", "oci"], "cloud", "AI CapEx → Cloud Infra"),
    # 宏观
    (["fed", "rate cut", "rate hike", "interest rate"], "macro", "Fed Policy → Macro"),
    (["cpi", "inflation"], "macro", "CPI/Inflation → Macro"),
    (["recession"], "macro", "Recession → Macro"),
    (["unemployment", "jobs report"], "macro", "Jobs → Macro"),
    (["oil", "crude"], "macro", "Oil → Macro"),
    # 消费电子
    (["iphone", "apple", "smartphone"], "edge_ai", "Smartphone → Edge AI"),
    (["ai glasses", "smart glasses"], "ai_glass", "AI Glasses → Supply Chain"),
]

# 行业码 → 主要受益公司（DB 有 industry_company 时动态取，这里是兜底）
INDUSTRY_FALLBACK_STOCKS = {
    "ai_chip": ["NVDA", "AMD", "MRVL"],
    "memory": ["MU"],
    "foundry": ["TSMC"],
    "network": ["MRVL", "NVDA"],
    "cloud": ["MSFT", "GOOGL", "ORCL"],
    "macro": [],
    "edge_ai": ["GOOGL", "META"],
    "ai_glass": ["688608.SH", "002241.SZ", "META"],
}


def map_event_to_stocks(event, consensus=None, persist=True):
    """单个事件 → 行业 + 股票信号列表
    event: prediction_event dict（含 id/title/category）
    consensus: 已有共识结果（可选，省一次计算）
    """
    if consensus is None:
        consensus = compute_consensus(event["id"], persist=False)
    if not consensus or consensus.get("probability") is None:
        return {"event_id": event["id"], "mapped": [], "reason": "无共识概率"}

    prob = consensus["probability"]
    momentum = consensus.get("momentum_24h") or 0
    direction, strength = direction_from_probability(prob, momentum)
    conf = confidence_from_consensus(consensus)

    # 1. 关键词匹配行业
    title = ((event.get("title") or "") + " " + (event.get("category") or "")).lower()
    matched_industry = None
    match_desc = ""
    for kws, ind_code, desc in KEYWORD_MAP:
        if any(k in title for k in kws):
            matched_industry = ind_code
            match_desc = desc
            break

    # 2. 行业 → 股票（优先 DB industry_company，兜底静态表）
    stocks = _stocks_for_industry(matched_industry) if matched_industry else []
    signals = []
    if direction != "neutral":
        for sym in stocks:
            sig = {
                "event_id": event["id"],
                "entity_type": "stock",
                "entity_symbol": sym,
                "direction": direction,
                "strength": strength,
                "confidence": conf,
                "probability": prob,
                "momentum_24h": consensus.get("momentum_24h"),
                "horizon": _horizon(event),
                "propagation_path": f"{match_desc} → {sym}",
            }
            if persist:
                repo.save_signal(**sig)
            signals.append(sig)

    result = {
        "event_id": event["id"],
        "title": event.get("title"),
        "category": event.get("category"),
        "probability": prob,
        "direction": direction,
        "strength": strength,
        "confidence": conf,
        "industry": matched_industry,
        "path": match_desc,
        "stocks": stocks,
        "signals": signals,
        "mapped": len(signals) > 0,
    }
    return result


def _stocks_for_industry(industry_code):
    """行业 → 股票：优先 industry_company（exposure_weight），兜底静态表"""
    if not industry_code:
        return []
    out = []
    try:
        from data.repositories import graph_repo
        rows = graph_repo.get_industry_companies(code=industry_code)
        for r in rows or []:
            sym = r.get("stock_symbol")
            if sym:
                out.append(sym)
    except Exception:
        pass
    if not out:
        out = INDUSTRY_FALLBACK_STOCKS.get(industry_code, [])
    return out


def _horizon(event):
    """事件到期日 → horizon：<30d short / <180d medium / else long"""
    end = event.get("end_time")
    if not end:
        return "medium"
    try:
        days = (end - datetime.now()).days
    except Exception:
        return "medium"
    if days <= 30:
        return "short"
    if days <= 180:
        return "medium"
    return "long"


def map_all_events(persist=True, category=None):
    """所有 open 事件 → 股票信号"""
    events = repo.list_events(status="open", category=category, limit=100)
    results = []
    for e in events:
        try:
            r = map_event_to_stocks(e, persist=persist)
            if r.get("mapped"):
                results.append(r)
        except Exception as ex:
            print(f"[prediction_map] event#{e['id']} 失败: {str(ex)[:80]}")
    return {"mapped_events": len(results), "results": results,
            "total_events": len(events)}


def stock_prediction_score(symbol):
    """股票 Prediction 成分分（0~100）：聚合该股全部预测信号
    方向 bullish → 高分；bearish → 低分；无信号 → 中性 50
    """
    rows = repo.get_signals(entity_type="stock", entity_symbol=symbol.upper(), limit=50)
    if not rows:
        return {"score": 50.0, "signals": [], "count": 0, "note": "无预测信号"}
    score = 50.0
    detail = []
    for r in rows[:20]:
        s = float(r["strength"] or 0)
        c = float(r["confidence"] or 0)
        # 强度×置信度加权，单条贡献 ±20 封顶
        score += max(-20.0, min(20.0, s * 20 * (0.5 + 0.5 * c)))
        detail.append({"event": r.get("event_title"), "direction": r["direction"],
                       "strength": s, "confidence": c,
                       "probability": float(r["probability"]) if r["probability"] is not None else None,
                       "path": r.get("propagation_path")})
    score = max(0.0, min(100.0, score))
    return {"score": round(score, 2), "signals": detail, "count": len(detail),
            "note": f"{len(detail)} 个预测信号聚合"}


if __name__ == "__main__":
    import json
    r = map_all_events(persist=True)
    print(f"mapped events: {r['mapped_events']}/{r['total_events']}")
    for x in r["results"][:5]:
        print(f"  [{x['category']}] {x['title'][:40]} p={x['probability']} "
              f"{x['direction']} ({x['strength']}) -> {x['stocks']}")
