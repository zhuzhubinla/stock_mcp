"""AI 分析管线：event / sentiment / relevance / impact / confidence
优先 LLM（DeepSeek，JSON 输出），无 key 或失败时回退规则引擎。
"""
import json

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, NEWS_ANALYZE_BATCH
from database import mysql_db as db
from .providers.base import NewsItem
from . import event_extractor

SYSTEM_PROMPT = (
    "你是专业的股票新闻分析器。给定一条新闻和涉及的股票，只输出 JSON：\n"
    '{"event_type": "earnings|guidance|revenue|profit|product_launch|product_delay|'
    'product_failure|m_and_a|partnership|contract|customer|supplier|regulation|lawsuit|'
    'government|management|analyst_upgrade|analyst_downgrade|insider_buy|insider_sell|'
    'financing|buyback|dividend|macro|cyber_attack|recall|bankruptcy|other",\n'
    '"sentiment": "positive|negative|neutral",\n'
    '"sentiment_score": -1.0到1.0的浮点数,\n'
    '"relevance_score": 0到1（该新闻与涉及股票的相关度）,\n'
    '"impact_score": 0到1（对股价的潜在影响大小）,\n'
    '"confidence": 0到1,\n'
    '"time_horizon": "1-5d"或"5-30d",\n'
    '"summary": "一句话摘要",\n'
    '"reasoning": "简要推理理由"}\n'
    "注意：impact 是影响力度，sentiment 是利好/利空方向，两者互相独立。"
)

POS_WORDS = ["beat", "surge", "record", "growth", "upgrade", "outperform", "win", "positive",
             "profit", "rally", "strong", "jump", "gain", "soar", "boost", "raise", "buyback",
             "dividend", "partnership", "launch", "expansion", "ahead of", "topping"]
NEG_WORDS = ["miss", "plunge", "downgrade", "lawsuit", "investigation", "weak", "loss", "cut",
             "decline", "fall", "recall", "ban", "risk", "delay", "probe", "fraud", "charge",
             "layoff", "slump", "penalty", "warn", "warning", "below"]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _llm_analyze(item, symbols_text):
    if not DEEPSEEK_API_KEY:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        user = (f"新闻标题: {item.title}\n"
                f"摘要: {item.summary or '无'}\n"
                f"正文: {(item.content or '')[:800]}\n"
                f"涉及股票: {symbols_text or '未知'}")
        last_err = None
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": user}],
                    temperature=0.2,
                    max_tokens=600,
                )
                content = (resp.choices[0].message.content or "").strip()
                # 剥离可能的 markdown 代码围栏
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:].strip()
                if content:
                    return _sanitize(json.loads(content), item)
                last_err = "空响应"
            except Exception as e:
                last_err = str(e)[:200]
        print(f"[analyzer] LLM 分析失败(重试后)，回退规则引擎: {last_err}")
        return None
    except Exception as e:
        print(f"[analyzer] LLM 客户端异常，回退规则引擎: {e}")
        return None


def _sanitize(data, item):
    def f(key, default):
        try:
            return float(data.get(key, default))
        except (TypeError, ValueError):
            return default

    event_type, _ = event_extractor.extract(item)
    sentiment = data.get("sentiment", "neutral")
    if sentiment not in ("positive", "negative", "neutral"):
        sentiment = "neutral"
    return {
        "event_type": data.get("event_type") or event_type,
        "sentiment": sentiment,
        "sentiment_score": round(_clamp(f("sentiment_score", 0), -1, 1), 4),
        "relevance_score": round(_clamp(f("relevance_score", 0.5), 0, 1), 4),
        "impact_score": round(_clamp(f("impact_score", 0.2), 0, 1), 4),
        "confidence": round(_clamp(f("confidence", 0.5), 0, 1), 4),
        "time_horizon": data.get("time_horizon") or "1-5d",
        "summary": (data.get("summary") or (item.summary or item.title))[:500],
        "reasoning": (data.get("reasoning") or "")[:1000],
    }


def _rule_analyze(item, symbols, event_type, matched_kws):
    text = f"{item.title or ''} {item.summary or ''}".lower()
    pos = sum(1 for w in POS_WORDS if w in text)
    neg = sum(1 for w in NEG_WORDS if w in text)
    if pos > neg:
        sentiment = "positive"
    elif neg > pos:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    raw = (pos - neg) / max(1, pos + neg)
    impact = event_extractor.IMPACT_BY_EVENT.get(event_type, 0.2)
    if matched_kws:
        impact = min(1.0, impact + 0.05 * len(matched_kws))
    relevance_scores = [float(s["relevance_score"]) for s in symbols
                        if s.get("relevance_score") is not None]
    relevance = max(relevance_scores, default=0.5)
    return {
        "event_type": event_type,
        "sentiment": sentiment,
        "sentiment_score": round(_clamp(raw * 1.2, -1, 1), 4),
        "relevance_score": round(_clamp(relevance, 0, 1), 4),
        "impact_score": round(_clamp(impact, 0, 1), 4),
        "confidence": 0.5,
        "time_horizon": event_extractor.TIME_HORIZON_BY_EVENT.get(event_type, "1-5d"),
        "summary": (item.summary or item.title)[:500],
        "reasoning": f"规则引擎: 事件={event_type}, 关键词={matched_kws or '无'}, 正词{pos}/负词{neg}",
    }


def analyze_one(item: NewsItem, symbols):
    """单条新闻分析，返回结构化结果 dict"""
    symbols_text = ", ".join(f"{s['symbol']}" for s in symbols)
    event_type, matched = event_extractor.extract(item)
    result = _llm_analyze(item, symbols_text)
    if result is None:
        result = _rule_analyze(item, symbols, event_type, matched)
    return result


def analyze_pending(limit=None, model="deepseek-v4-flash"):
    """分析所有 status='new' 的新闻；写 analysis，落事件，标记完成"""
    limit = limit or NEWS_ANALYZE_BATCH
    rows = db.get_unanalyzed_news(limit)
    done = 0
    for row in rows:
        item = NewsItem(
            source_news_id=row["source_news_id"] or "",
            title=row["title"] or "",
            summary=row["summary"] or "",
            content=row["content"] or "",
            url=row["url"] or "",
            publisher=row["publisher"] or "",
            published_at=row["published_at"],
        )
        symbols = db.get_news_symbols(row["id"])
        if not symbols:
            db.mark_news_analyzed(row["id"])
            continue
        result = analyze_one(item, symbols)
        db.upsert_news_analysis(
            row["id"], model, "1.0", result["event_type"], result["sentiment"],
            result["sentiment_score"], result["relevance_score"], result["impact_score"],
            result["confidence"], result["time_horizon"], result["summary"], result["reasoning"],
        )
        # 高影响事件落库（stock_news_event）并回链
        if result["event_type"] != "other" and result["impact_score"] >= 0.5:
            event_id = db.insert_event(
                result["event_type"], row["title"], result["summary"],
                row["published_at"], result["impact_score"], result["confidence"],
            )
            db.set_news_event(row["id"], event_id)
        db.mark_news_analyzed(row["id"])
        done += 1
    return {"analyzed": done, "pending_total": len(rows)}
