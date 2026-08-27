"""Summarizer：研究报告摘要生成（Detailed Technical Design 第 13 节 AI 层）
拆自 analyst.py 的摘要逻辑：LLM 优先，规则兜底。
"""
import sys, json
sys.path.append("/home/admin/stock_agent")

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

SYSTEM_PROMPT = (
    "你是专业的股票研究分析师。基于给定的结构化分析结果，输出简洁的中文研究报告，"
    "包含：核心结论、关键驱动、风险提示。不超过 300 字。直接输出正文，不要 JSON。"
)


def summarize(stock_first_result=None, industry_result=None, factor_result=None,
              symbol=None):
    """把结构化分析结果转成研究报告摘要（LLM；无 key 回退模板）"""
    payload = {
        "symbol": symbol or (stock_first_result or {}).get("symbol"),
        "stock_first": stock_first_result,
        "industry": industry_result,
        "factor": factor_result,
    }
    if not DEEPSEEK_API_KEY:
        return _fallback_summary(payload)
    try:
        import requests
        r = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)[:12000]},
                ],
                "temperature": 0.4,
                "max_tokens": 600,
            },
            timeout=60,
        )
        r.raise_for_status()
        return {"symbol": payload["symbol"], "report": r.json()["choices"][0]["message"]["content"],
                "model": DEEPSEEK_MODEL}
    except Exception as e:
        return {**payload, "report": _fallback_summary(payload)["report"], "error": str(e)}


def _fallback_summary(payload):
    """规则兜底：从结构化数据提取要点"""
    sym = payload.get("symbol") or ""
    lines = [f"【{sym} 研究摘要】" if sym else "【研究摘要】"]
    sf = payload.get("stock_first") or {}
    for st in sf.get("steps", []):
        if st["step"] == "driver_engine" and st["data"]:
            pos = [d for d in st["data"] if d["impact_direction"] == "positive"]
            neg = [d for d in st["data"] if d["impact_direction"] == "negative"]
            lines.append(f"驱动因子：正向 {len(pos)} 个 / 负向 {len(neg)} 个")
            if pos:
                lines.append("正向：" + "、".join(d["driver"] for d in pos[:5]))
        if st["step"] == "scenario_engine":
            sc = st["data"].get("scenarios", {})
            if sc:
                lines.append("情景EPS：" + " / ".join(
                    f"{k}={v['eps']}" for k, v in sc.items()))
        if st["step"] == "valuation_engine":
            pb = st["data"].get("price_band", {})
            if pb and "base" in pb:
                lines.append(f"目标价区间：{pb['base']['target_low']}~{pb['base']['target_high']}")
    ind = payload.get("industry") or {}
    if ind.get("industry"):
        lines.append(f"行业[{ind['industry']}]公司数 {ind.get('company_count', 0)}，"
                     f"Top: " + "、".join(c["symbol"] for c in ind.get("companies", [])[:5]))
    fac = payload.get("factor") or {}
    if fac.get("ranking"):
        lines.append("因子弹性Top：" + "、".join(
            f"{x['symbol']}({x['elasticity']})" for x in fac["ranking"][:5]))
    lines.append("（规则摘要，未配置 DEEPSEEK_API_KEY）")
    return {"report": "\n".join(lines)}
