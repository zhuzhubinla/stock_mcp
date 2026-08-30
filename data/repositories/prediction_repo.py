"""Prediction Repository：prediction_* 表读写（设计文档 18.1）"""
import sys
import json
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn


# ---------- source ----------
def get_source(source_code):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM prediction_source WHERE code=%s", (source_code,))
        return cur.fetchone()


def list_sources(enabled_only=True):
    with get_conn() as conn, conn.cursor() as cur:
        if enabled_only:
            cur.execute("SELECT * FROM prediction_source WHERE enabled=1 ORDER BY priority")
        else:
            cur.execute("SELECT * FROM prediction_source ORDER BY priority")
        return cur.fetchall()


# ---------- event ----------
def upsert_event(external_id, title, category, start_time, end_time, status="open", description=None):
    """按 external_id 幂等 upsert，返回 event_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM prediction_event WHERE title=%s", (title,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE prediction_event SET category=COALESCE(%s, category),
                  start_time=COALESCE(%s, start_time), end_time=COALESCE(%s, end_time),
                  status=%s
                WHERE id=%s
            """, (category, start_time, end_time, status, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO prediction_event (title, category, start_time, end_time, status, description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, category, start_time, end_time, status, description))
        return cur.lastrowid


def get_event(event_id=None, title=None):
    with get_conn() as conn, conn.cursor() as cur:
        if event_id:
            cur.execute("SELECT * FROM prediction_event WHERE id=%s", (event_id,))
        elif title:
            cur.execute("SELECT * FROM prediction_event WHERE title=%s", (title,))
        else:
            return None
        return cur.fetchone()


def list_events(status="open", category=None, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        sql = "SELECT * FROM prediction_event WHERE 1=1"
        params = []
        if status:
            sql += " AND status=%s"
            params.append(status)
        if category:
            sql += " AND category=%s"
            params.append(category)
        sql += " ORDER BY end_time ASC LIMIT %s"
        params.append(limit)
        cur.execute(sql, tuple(params))
        return cur.fetchall()


# ---------- market ----------
def upsert_market(event_id, source_id, external_id, title, market_type="binary",
                  status="active", yes_ask=None, yes_bid=None, last_price=None,
                  volume=None, open_interest=None, liquidity=None, close_time=None, detail=None):
    """按 (source_id, external_id) 幂等 upsert，返回 market_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM prediction_market WHERE source_id=%s AND external_id=%s",
                    (source_id, external_id))
        row = cur.fetchone()
        now = datetime.now()
        if row:
            cur.execute("""
                UPDATE prediction_market SET event_id=COALESCE(%s, event_id),
                  title=COALESCE(%s, title), market_type=COALESCE(%s, market_type),
                  status=%s, yes_ask=%s, yes_bid=%s, last_price=%s, volume=%s,
                  open_interest=%s, liquidity=%s, close_time=COALESCE(%s, close_time),
                  detail=COALESCE(%s, detail), last_sync_at=%s
                WHERE id=%s
            """, (event_id, title, market_type, status, yes_ask, yes_bid, last_price,
                  volume, open_interest, liquidity, close_time,
                  json.dumps(detail, ensure_ascii=False) if detail else None, now, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO prediction_market (event_id, source_id, external_id, title, market_type,
                                           status, yes_ask, yes_bid, last_price, volume,
                                           open_interest, liquidity, close_time, detail, last_sync_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (event_id, source_id, external_id, title, market_type, status,
              yes_ask, yes_bid, last_price, volume, open_interest, liquidity,
              close_time, json.dumps(detail, ensure_ascii=False) if detail else None, now))
        return cur.lastrowid


def get_market(market_id=None, external_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        if market_id:
            cur.execute("SELECT * FROM prediction_market WHERE id=%s", (market_id,))
        elif external_id:
            cur.execute("SELECT * FROM prediction_market WHERE external_id=%s", (external_id,))
        else:
            return None
        return cur.fetchone()


def list_markets(status="active", source_code=None, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """SELECT m.*, s.code AS source_code, s.name AS source_name,
                        e.title AS event_title, e.category AS event_category
                 FROM prediction_market m
                 JOIN prediction_source s ON s.id = m.source_id
                 LEFT JOIN prediction_event e ON e.id = m.event_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += " AND m.status=%s"
            params.append(status)
        if source_code:
            sql += " AND s.code=%s"
            params.append(source_code)
        sql += " ORDER BY m.last_sync_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, tuple(params))
        return cur.fetchall()


# ---------- outcome ----------
def upsert_outcome(market_id, outcome_key, outcome_label, probability):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO prediction_outcome (market_id, outcome_key, outcome_label, probability, last_sync_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE outcome_label=VALUES(outcome_label),
              probability=VALUES(probability), last_sync_at=NOW()
        """, (market_id, outcome_key, outcome_label, probability))


def get_outcomes(market_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM prediction_outcome WHERE market_id=%s", (market_id,))
        return cur.fetchall()


# ---------- probability history ----------
def save_probability(market_id, outcome_key, probability, observed_at=None,
                     volume=None, open_interest=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT IGNORE INTO prediction_probability
                (market_id, outcome_key, probability, volume, open_interest, observed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (market_id, outcome_key, probability, volume, open_interest,
              observed_at or datetime.now()))


def get_probability_history(market_id, outcome_key="yes", hours=24):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT probability, observed_at FROM prediction_probability
            WHERE market_id=%s AND outcome_key=%s AND observed_at >= NOW() - INTERVAL %s HOUR
            ORDER BY observed_at ASC
        """, (market_id, outcome_key, hours))
        return cur.fetchall()


# ---------- consensus ----------
def save_consensus(event_id, probability, dispersion, source_count,
                   momentum_24h=None, momentum_7d=None, detail=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO prediction_consensus
                (event_id, timestamp, probability, dispersion, source_count,
                 momentum_24h, momentum_7d, detail)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)
        """, (event_id, probability, dispersion, source_count,
              momentum_24h, momentum_7d,
              json.dumps(detail, ensure_ascii=False) if detail else None))
        return cur.lastrowid


def get_consensus_history(event_id, limit=10):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM prediction_consensus WHERE event_id=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (event_id, limit))
        return cur.fetchall()


# ---------- signal ----------
def save_signal(event_id, entity_type, entity_symbol, direction, strength, confidence,
                probability, momentum_24h, horizon, propagation_path):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO prediction_signal
                (event_id, entity_type, entity_symbol, direction, strength, confidence,
                 probability, momentum_24h, horizon, propagation_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (event_id, entity_type, entity_symbol, direction, strength, confidence,
              probability, momentum_24h, horizon, propagation_path))
        return cur.lastrowid


def get_signals(entity_type=None, entity_symbol=None, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """SELECT s.*, e.title AS event_title, e.category AS event_category
                 FROM prediction_signal s
                 LEFT JOIN prediction_event e ON e.id = s.event_id
                 WHERE 1=1"""
        params = []
        if entity_type:
            sql += " AND s.entity_type=%s"
            params.append(entity_type)
        if entity_symbol:
            sql += " AND s.entity_symbol=%s"
            params.append(entity_symbol)
        sql += " ORDER BY s.created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, tuple(params))
        return cur.fetchall()
