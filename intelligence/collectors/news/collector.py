"""采集编排：fetch → normalize → dedup → entity resolve → store → log

多源支持：默认遍历 PROVIDERS 里所有已配置（is_configured）的源；
也可用 source_codes 指定子集。单源失败不影响其他源。
"""
from datetime import datetime, timedelta

from config import NEWS_FETCH_HOURS
from intelligence.repositories import mysql_db as db
from .providers import get_provider, PROVIDERS
from .normalizer import normalize
from .deduplicator import find_duplicate
from .entity_resolver import resolve, COMPANIES


def _collect_source(source_code, symbols, start, end):
    """单个源的采集逻辑，返回该源统计 dict。"""
    provider = get_provider(source_code)
    source_id = db.ensure_source(source_code, name=provider.name,
                                 api_type=source_code, base_url=provider.base_url)
    summary = {"source": source_code, "fetched": 0, "inserted": 0,
               "duplicated": 0, "errors": 0, "logs": []}

    for symbol in symbols:
        t0 = datetime.now()
        try:
            raw_items = provider.get_news(symbol, start, end)
        except Exception as e:
            db.insert_fetch_log(source_id, symbol, start, end, 0, 0, 0, 1, "error", str(e))
            summary["errors"] += 1
            summary["logs"].append({"symbol": symbol, "status": "error", "error": str(e)})
            continue

        fetched = inserted = duplicated = 0
        for raw in raw_items:
            item = normalize(raw, source_code)
            if item is None:
                continue
            fetched += 1
            existing_id, level = find_duplicate(db, source_id, item)
            if existing_id:
                duplicated += 1
                # 跨 symbol 的同一新闻：给当前 symbol 补 M2M 关联（非主）
                db.insert_news_symbol(existing_id, symbol, COMPANIES.get(symbol),
                                      None, 1, 0)
                continue
            news_id = db.insert_news(
                source_id, item.source_news_id, item.title, item.summary, item.content,
                item.url, item.publisher, item.published_at,
                author=item.author, image_url=item.image_url, language=item.language,
            )
            if not news_id:
                duplicated += 1
                continue
            inserted += 1
            for ent in resolve(item, primary_symbol=symbol):
                db.insert_news_symbol(news_id, ent["symbol"], ent["company_name"],
                                      ent["relevance_score"], ent["mention_count"],
                                      ent["is_primary"])

        elapsed_ms = int((datetime.now() - t0).total_seconds() * 1000)
        db.insert_fetch_log(source_id, symbol, start, end, fetched, inserted, duplicated,
                            0, "ok", response_time_ms=elapsed_ms)
        summary["fetched"] += fetched
        summary["inserted"] += inserted
        summary["duplicated"] += duplicated
        summary["logs"].append({"symbol": symbol, "status": "ok", "fetched": fetched,
                                "inserted": inserted, "duplicated": duplicated})

    return summary


def collect(symbols, hours=None, source_codes=None):
    """采集一批 symbol 的新闻（多源）。

    source_codes: None=所有已配置源；也可传单个 code 或 list。
    返回统计 dict，含 sources 明细。
    """
    if isinstance(source_codes, str):
        source_codes = [source_codes]
    if source_codes is None:
        source_codes = [code for code, cls in PROVIDERS.items() if cls.is_configured()]

    hours = hours or NEWS_FETCH_HOURS
    end = datetime.now()
    start = end - timedelta(hours=hours)

    summary = {"sources": list(source_codes), "symbols": list(symbols),
               "fetched": 0, "inserted": 0, "duplicated": 0, "errors": 0, "logs": []}
    per_source = {}
    for code in source_codes:
        try:
            s = _collect_source(code, symbols, start, end)
        except Exception as e:
            # 该源整体不可用（如缺 key / 初始化失败）：记日志，不中断其他源
            s = {"source": code, "fetched": 0, "inserted": 0, "duplicated": 0,
                 "errors": 1, "logs": [{"status": "source_error", "error": str(e)}]}
        per_source[code] = s
        for k in ("fetched", "inserted", "duplicated", "errors"):
            summary[k] += s[k]
        summary["logs"].extend(s["logs"])
    summary["per_source"] = per_source
    return summary
