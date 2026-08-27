"""MySQL 访问层：连接、建表、仓储操作"""
import json
import pymysql
from datetime import datetime

import sys
sys.path.append("/home/admin/stock_agent")
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB


def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


# ---------- stock ----------
def upsert_stock(symbol, name=None, exchange=None, sector=None, industry=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock (symbol, name, exchange, sector, industry)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              name=COALESCE(VALUES(name), name),
              exchange=COALESCE(VALUES(exchange), exchange),
              sector=COALESCE(VALUES(sector), sector),
              industry=COALESCE(VALUES(industry), industry)
        """, (symbol, name, exchange, sector, industry))


def get_stock(symbol):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM stock WHERE symbol=%s", (symbol,))
        return cur.fetchone()


# ---------- stock_price ----------
def upsert_price(symbol, ts, open_, high, low, close, volume, source="finnhub"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_price (symbol, timestamp, open, high, low, close, volume, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              open=VALUES(open), high=VALUES(high), low=VALUES(low),
              close=VALUES(close),
              volume=COALESCE(VALUES(volume), volume),
              source=VALUES(source)
        """, (symbol, ts, open_, high, low, close, volume, source))


def get_latest_price(symbol):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM stock_price WHERE symbol=%s
            ORDER BY timestamp DESC LIMIT 1
        """, (symbol,))
        return cur.fetchone()


def get_prices(symbol, days=90):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM stock_price WHERE symbol=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (symbol, days))
        rows = cur.fetchall()
    return list(reversed(rows))


def price_fresh(symbol, ttl):
    row = get_latest_price(symbol)
    if not row:
        return False
    age = (datetime.now() - row["timestamp"]).total_seconds()
    return age < ttl


# ---------- stock_news（Phase5 架构） ----------
def ensure_source(code, name=None, api_type=None, base_url=None, priority=100):
    """获取或创建新闻源，返回 source_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM news_source WHERE code=%s", (code,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("""
            INSERT INTO news_source (name, code, api_type, base_url, enabled, priority)
            VALUES (%s, %s, %s, %s, 1, %s)
        """, (name or code, code, api_type, base_url, priority))
        return cur.lastrowid


def find_dup_news(source_id, source_news_id, url_hash, content_hash):
    """四级去重查找：返回 (existing_id, dup_level)，0 = 无重复"""
    with get_conn() as conn, conn.cursor() as cur:
        if source_news_id:
            cur.execute("SELECT id FROM stock_news WHERE source_id=%s AND source_news_id=%s",
                        (source_id, source_news_id))
            row = cur.fetchone()
            if row:
                return row["id"], 1
        if url_hash:
            cur.execute("SELECT id FROM stock_news WHERE url_hash=%s", (url_hash,))
            row = cur.fetchone()
            if row:
                return row["id"], 2
        if content_hash:
            cur.execute("SELECT id FROM stock_news WHERE content_hash=%s", (content_hash,))
            row = cur.fetchone()
            if row:
                return row["id"], 3
    return None, 0


def insert_news(source_id, source_news_id, title, summary, content, url, publisher,
                published_at, author=None, image_url=None, language="en"):
    """插入原始新闻，返回 news_id；重复返回 None"""
    import hashlib
    url_hash = hashlib.sha256((url or "").encode("utf-8")).hexdigest()
    content_hash = hashlib.sha256(f"{title}|{summary or ''}".encode("utf-8")).hexdigest()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_news (source_id, source_news_id, title, summary, content,
                                    url, image_url, author, publisher, language,
                                    published_at, content_hash, url_hash, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """, (source_id, source_news_id, title, summary, content, url, image_url,
               author, publisher, language, published_at, content_hash, url_hash))
        return cur.lastrowid


def get_news_by_id(news_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM stock_news WHERE id=%s", (news_id,))
        return cur.fetchone()


def get_unanalyzed_news(limit=10):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM stock_news WHERE status='new'
            ORDER BY published_at DESC LIMIT %s
        """, (limit,))
        return cur.fetchall()


def mark_news_analyzed(news_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE stock_news SET status='analyzed' WHERE id=%s", (news_id,))


def set_news_event(news_id, event_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE stock_news SET event_id=%s WHERE id=%s", (event_id, news_id))


# ---------- stock_news_symbol ----------
def insert_news_symbol(news_id, symbol, company_name=None, relevance_score=None,
                       mention_count=1, is_primary=0):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT IGNORE INTO stock_news_symbol
                (news_id, symbol, company_name, relevance_score, mention_count, is_primary)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (news_id, symbol, company_name, relevance_score, mention_count, is_primary))


def get_news_symbols(news_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, company_name, relevance_score, mention_count, is_primary
            FROM stock_news_symbol WHERE news_id=%s
        """, (news_id,))
        return cur.fetchall()


def get_news(symbol, limit=10, hours=None):
    """按 symbol 取新闻（含最新 AI 分析结果），hours=None 不设时间窗"""
    sql = """
        SELECT n.id, n.title, n.summary, n.content, n.url, n.publisher, n.published_at,
               n.language, n.status, n.source_id, n.source_news_id,
               a.sentiment, a.sentiment_score, a.impact_score, a.relevance_score,
               a.event_type, a.time_horizon, a.model
        FROM stock_news n
        JOIN stock_news_symbol sns ON sns.news_id = n.id
        LEFT JOIN (
            SELECT news_id, sentiment, sentiment_score, impact_score, relevance_score,
                   event_type, time_horizon, model
            FROM stock_news_analysis
            WHERE id IN (SELECT MAX(id) FROM stock_news_analysis GROUP BY news_id)
        ) a ON a.news_id = n.id
        WHERE sns.symbol = %s
    """
    params = [symbol]
    if hours:
        sql += " AND n.published_at >= NOW() - INTERVAL %s HOUR"
        params.append(hours)
    sql += " ORDER BY n.published_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall()


def get_news_between(symbol, start_dt, end_dt, limit=20):
    """时间窗口内新闻（异常归因用）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT n.id, n.title, n.published_at, a.sentiment, a.sentiment_score,
                   a.impact_score, a.relevance_score, a.event_type
            FROM stock_news n
            JOIN stock_news_symbol sns ON sns.news_id = n.id
            LEFT JOIN stock_news_analysis a ON a.news_id = n.id
            WHERE sns.symbol=%s AND n.published_at BETWEEN %s AND %s
            ORDER BY n.published_at DESC LIMIT %s
        """, (symbol, start_dt, end_dt, limit))
        return cur.fetchall()


def news_fresh(symbol, ttl, min_count=1):
    rows = get_news(symbol, limit=1)
    if not rows or len(rows) < min_count:
        return False
    age = (datetime.now() - rows[0]["published_at"]).total_seconds()
    return age < ttl


# ---------- stock_news_analysis ----------
def upsert_news_analysis(news_id, model, model_version, event_type, sentiment,
                         sentiment_score, relevance_score, impact_score, confidence,
                         time_horizon, summary, reasoning):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_news_analysis
                (news_id, model, model_version, event_type, sentiment, sentiment_score,
                 relevance_score, impact_score, confidence, time_horizon, summary, reasoning)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              event_type=VALUES(event_type), sentiment=VALUES(sentiment),
              sentiment_score=VALUES(sentiment_score), relevance_score=VALUES(relevance_score),
              impact_score=VALUES(impact_score), confidence=VALUES(confidence),
              time_horizon=VALUES(time_horizon), summary=VALUES(summary),
              reasoning=VALUES(reasoning), analyzed_at=NOW()
        """, (news_id, model, model_version, event_type, sentiment, sentiment_score,
               relevance_score, impact_score, confidence, time_horizon, summary, reasoning))


# ---------- stock_news_event ----------
def insert_event(event_type, title, description, event_time, impact_score=None, confidence=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_news_event (event_type, title, description, event_time,
                                          impact_score, confidence, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
        """, (event_type, title, description, event_time, impact_score, confidence))
        return cur.lastrowid


def get_events(symbol, hours=24, event_type=None, limit=20):
    sql = """
        SELECT DISTINCT e.id, e.event_type, e.title, e.description, e.event_time,
               e.impact_score, e.confidence
        FROM stock_news_event e
        JOIN stock_news n ON n.event_id = e.id
        JOIN stock_news_symbol sns ON sns.news_id = n.id
        WHERE sns.symbol=%s AND e.event_time >= NOW() - INTERVAL %s HOUR
    """
    params = [symbol, hours]
    if event_type:
        sql += " AND e.event_type = %s"
        params.append(event_type)
    sql += " ORDER BY e.event_time DESC, e.impact_score DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall()


# ---------- news_fetch_log ----------
def insert_fetch_log(source_id, symbol, start_time, end_time, fetched_count=0,
                     inserted_count=0, duplicate_count=0, error_count=0,
                     status="ok", error_message=None, response_time_ms=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO news_fetch_log (source_id, symbol, start_time, end_time,
                                        fetched_count, inserted_count, duplicate_count,
                                        error_count, status, error_message, response_time_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (source_id, symbol, start_time, end_time, fetched_count, inserted_count,
               duplicate_count, error_count, status, error_message, response_time_ms))


# ---------- stock_fundamental ----------
def upsert_fundamental(symbol, metric, value, period=None, source="finnhub"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_fundamental (symbol, metric, value, period, source)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE value=VALUES(value), source=VALUES(source)
        """, (symbol, metric, value, period, source))


def get_fundamentals(symbol):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT metric, value, period, source FROM stock_fundamental
            WHERE symbol=%s ORDER BY metric
        """, (symbol,))
        return cur.fetchall()


def fundamentals_fresh(symbol, ttl):
    rows = get_fundamentals(symbol)
    if not rows:
        return False
    # 用最近一条的插入时间近似判断：查 stock_fundamental 无时间戳列，用 stock 更新简化
    return len(rows) > 0


# ---------- stock_signal ----------
def save_signal(symbol, signal_type, score, value, description):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_signal (symbol, timestamp, signal_type, score, value, description)
            VALUES (%s, NOW(), %s, %s, %s, %s)
        """, (symbol, signal_type, score, value, description))


def get_signals(symbol, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM stock_signal WHERE symbol=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (symbol, limit))
        return cur.fetchall()


# ---------- stock_analysis ----------
def save_analysis(symbol, result, analysis_type="general", model=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_analysis (symbol, timestamp, analysis_type, result, model)
            VALUES (%s, NOW(), %s, %s, %s)
        """, (symbol, analysis_type, json.dumps(result, ensure_ascii=False, default=str), model))


def get_analysis(symbol, limit=10):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM stock_analysis WHERE symbol=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (symbol, limit))
        rows = cur.fetchall()
    for r in rows:
        if isinstance(r.get("result"), str):
            try:
                r["result"] = json.loads(r["result"])
            except Exception:
                pass
    return rows


if __name__ == "__main__":
    upsert_stock("NVDA", name="NVIDIA Corp", exchange="NASDAQ")
    print(get_stock("NVDA"))
    upsert_price("NVDA", datetime.now().replace(second=0, microsecond=0), 100, 105, 99, 103, 1000000)
    print(get_latest_price("NVDA"))
