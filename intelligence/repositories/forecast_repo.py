"""Forecast 仓储层：company_forecast / industry_forecast / financial_model / valuation
对应文档第 5 节与 11 节（Revenue/EPS Model、Bull/Base/Bear 情景）。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from database.mysql_db import get_conn


# ---------- company_forecast ----------
def upsert_company_forecast(company_id, metric, period, value, business_segment_id=None,
                            confidence=None, model="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_forecast (company_id, business_segment_id, metric, period,
                                          value, confidence, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              value=VALUES(value), confidence=COALESCE(VALUES(confidence), confidence)
        """, (company_id, business_segment_id, metric, period, value, confidence, model))
        return cur.lastrowid


def get_company_forecasts(company_id=None, symbol=None, metric=None, period=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT cf.*, c.name AS company_name, c.stock_symbol,
                   bs.name AS segment_name
            FROM company_forecast cf
            JOIN company c ON c.id = cf.company_id
            LEFT JOIN business_segment bs ON bs.id = cf.business_segment_id
        """
        params = []
        if symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE cf.company_id=%s"
            params.append(company_id)
        if metric:
            sql += " AND cf.metric=%s" if params else " WHERE cf.metric=%s"
            params.append(metric)
        if period:
            sql += " AND cf.period=%s" if params else " WHERE cf.period=%s"
            params.append(period)
        sql += " ORDER BY cf.period DESC, cf.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- industry_forecast ----------
def upsert_industry_forecast(industry_id, indicator_name, period, value,
                             confidence=None, model="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_forecast (industry_id, indicator_name, period, value,
                                           confidence, model)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              value=VALUES(value), confidence=COALESCE(VALUES(confidence), confidence)
        """, (industry_id, indicator_name, period, value, confidence, model))
        return cur.lastrowid


def get_industry_forecasts(industry_id=None, indicator_name=None, period=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT f.*, i.name AS industry_name FROM industry_forecast f
            JOIN industry i ON i.id = f.industry_id
        """
        params = []
        if industry_id:
            sql += " WHERE f.industry_id=%s"
            params.append(industry_id)
        if indicator_name:
            sql += " AND f.indicator_name=%s" if params else " WHERE f.indicator_name=%s"
            params.append(indicator_name)
        if period:
            sql += " AND f.period=%s" if params else " WHERE f.period=%s"
            params.append(period)
        sql += " ORDER BY f.period DESC, f.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- financial_model（Bull/Base/Bear 情景） ----------
def upsert_financial_model(company_id, scenario, period, revenue=None, gross_profit=None,
                           operating_income=None, net_income=None, eps=None, fcf=None,
                           model="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO financial_model (company_id, scenario, period, revenue, gross_profit,
                                         operating_income, net_income, eps, fcf, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              revenue=VALUES(revenue), gross_profit=VALUES(gross_profit),
              operating_income=VALUES(operating_income), net_income=VALUES(net_income),
              eps=VALUES(eps), fcf=VALUES(fcf)
        """, (company_id, scenario, period, revenue, gross_profit, operating_income,
               net_income, eps, fcf, model))
        return cur.lastrowid


def get_financial_models(company_id=None, symbol=None, scenario=None, period=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT fm.*, c.name AS company_name, c.stock_symbol
            FROM financial_model fm JOIN company c ON c.id = fm.company_id
        """
        params = []
        if symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE fm.company_id=%s"
            params.append(company_id)
        if scenario:
            sql += " AND fm.scenario=%s" if params else " WHERE fm.scenario=%s"
            params.append(scenario)
        if period:
            sql += " AND fm.period=%s" if params else " WHERE fm.period=%s"
            params.append(period)
        sql += " ORDER BY fm.period DESC, fm.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- valuation ----------
def upsert_valuation(company_id, method, value, scenario=None, target_price=None,
                     as_of=None, model="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO valuation (company_id, method, scenario, value, target_price,
                                   as_of, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (company_id, method, scenario, value, target_price, as_of, model))
        return cur.lastrowid


def get_valuations(company_id=None, symbol=None, method=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT v.*, c.name AS company_name, c.stock_symbol
            FROM valuation v JOIN company c ON c.id = v.company_id
        """
        params = []
        if symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE v.company_id=%s"
            params.append(company_id)
        if method:
            sql += " AND v.method=%s" if params else " WHERE v.method=%s"
            params.append(method)
        sql += " ORDER BY v.as_of DESC, v.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- source / event ----------
def upsert_source(code, name, url=None, source_type="api"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM source WHERE code=%s", (code,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO source (code, name, url, source_type) VALUES (%s,%s,%s,%s)",
                    (code, name, url, source_type))
        return cur.lastrowid


def insert_event(event_type, title, description=None, event_time=None,
                 impact_score=None, confidence=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO event (event_type, title, description, event_time,
                               impact_score, confidence, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
        """, (event_type, title, description, event_time, impact_score, confidence))
        return cur.lastrowid


def get_events(event_type=None, hours=168, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        sql = "SELECT * FROM event WHERE event_time >= NOW() - INTERVAL %s HOUR"
        params = [hours]
        if event_type:
            sql += " AND event_type=%s"
            params.append(event_type)
        sql += " ORDER BY event_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()
