"""Forecast 仓储层：company_forecast / industry_forecast / financial_model(+line) / valuation / source / event
依据《Detailed Technical Design》第 11-14 节字段级设计。
"""
import sys, json
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn


def _to_date(period):
    import datetime
    if period is None or isinstance(period, (datetime.date, datetime.datetime)):
        return period
    s = str(period).strip()
    if len(s) == 4 and s.isdigit():
        return f"{s}-01-01"
    if len(s) == 6 and s[4] == "Q":
        q = {"1": "01", "2": "04", "3": "07", "4": "10"}.get(s[5], "01")
        return f"{s[:4]}-{q}-01"
    if len(s) == 7 and s[4] == "-":
        return f"{s}-01"
    if len(s) >= 10:
        return s[:10]
    return s


# ---------- company_forecast ----------
def upsert_company_forecast(company_id, metric, period, value, business_segment_id=None,
                            scenario="base", low_value=None, high_value=None,
                            confidence=None, model_version="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_forecast (company_id, business_segment_id, metric, period,
                                          scenario, value, low_value, high_value,
                                          confidence, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              value=VALUES(value), low_value=COALESCE(VALUES(low_value), low_value),
              high_value=COALESCE(VALUES(high_value), high_value),
              confidence=COALESCE(VALUES(confidence), confidence)
        """, (company_id, business_segment_id, metric, _to_date(period), scenario,
              value, low_value, high_value, confidence, model_version))
        return cur.lastrowid


def get_company_forecasts(company_id=None, symbol=None, metric=None, period=None, scenario=None):
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
            params.append(_to_date(period))
        if scenario:
            sql += " AND cf.scenario=%s" if params else " WHERE cf.scenario=%s"
            params.append(scenario)
        sql += " ORDER BY cf.period DESC, cf.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- industry_forecast ----------
def upsert_industry_forecast(industry_id, indicator_code, period, value,
                             scenario="base", low_value=None, high_value=None,
                             confidence=None, model_version="intelligence-v1", source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_forecast (industry_id, indicator_code, period, scenario,
                                           value, low_value, high_value, confidence,
                                           model_version, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              value=VALUES(value), low_value=COALESCE(VALUES(low_value), low_value),
              high_value=COALESCE(VALUES(high_value), high_value),
              confidence=COALESCE(VALUES(confidence), confidence)
        """, (industry_id, indicator_code, _to_date(period), scenario, value,
              low_value, high_value, confidence, model_version, source_id))
        return cur.lastrowid


def get_industry_forecasts(industry_id=None, indicator_code=None, period=None, scenario=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT f.*, i.name AS industry_name FROM industry_forecast f
            JOIN industry i ON i.id = f.industry_id
        """
        params = []
        if industry_id:
            sql += " WHERE f.industry_id=%s"
            params.append(industry_id)
        if indicator_code:
            sql += " AND f.indicator_code=%s" if params else " WHERE f.indicator_code=%s"
            params.append(indicator_code)
        if period:
            sql += " AND f.period=%s" if params else " WHERE f.period=%s"
            params.append(_to_date(period))
        if scenario:
            sql += " AND f.scenario=%s" if params else " WHERE f.scenario=%s"
            params.append(scenario)
        sql += " ORDER BY f.period DESC, f.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- financial_model（模型头 + 明细行） ----------
def upsert_financial_model(company_id, name="Intelligence Model", model_type="bottom_up",
                           version="v1", base_period=None, forecast_start=None,
                           forecast_end=None, status="active"):
    """创建/取回模型头，返回 model_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM financial_model WHERE company_id=%s AND name=%s AND version=%s
        """, (company_id, name, version))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("""
            INSERT INTO financial_model (company_id, name, model_type, version,
                                         base_period, forecast_start, forecast_end, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (company_id, name, model_type, version, _to_date(base_period),
              _to_date(forecast_start), _to_date(forecast_end), status))
        return cur.lastrowid


def upsert_financial_model_line(model_id, metric, period, value, business_segment_id=None,
                                assumption_type="derived", source_driver_id=None, formula=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM financial_model_line
            WHERE model_id=%s AND metric=%s AND period=%s
              AND COALESCE(business_segment_id,0)=COALESCE(%s,0)
        """, (model_id, metric, _to_date(period), business_segment_id))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE financial_model_line SET value=%s, assumption_type=%s,
                  source_driver_id=COALESCE(%s, source_driver_id), formula=COALESCE(%s, formula)
                WHERE id=%s
            """, (value, assumption_type, source_driver_id, formula, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO financial_model_line (model_id, business_segment_id, metric, period,
                                              value, assumption_type, source_driver_id, formula)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (model_id, business_segment_id, metric, _to_date(period), value,
              assumption_type, source_driver_id, formula))
        return cur.lastrowid


def get_financial_model_lines(model_id=None, company_id=None, symbol=None, metric=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT fml.*, fm.name AS model_name, fm.version, fm.model_type,
                   c.name AS company_name, c.stock_symbol, bs.name AS segment_name
            FROM financial_model_line fml
            JOIN financial_model fm ON fm.id = fml.model_id
            JOIN company c ON c.id = fm.company_id
            LEFT JOIN business_segment bs ON bs.id = fml.business_segment_id
        """
        params = []
        if model_id:
            sql += " WHERE fml.model_id=%s"
            params.append(model_id)
        elif symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE fm.company_id=%s"
            params.append(company_id)
        if metric:
            sql += " AND fml.metric=%s" if params else " WHERE fml.metric=%s"
            params.append(metric)
        sql += " ORDER BY fml.period, fml.metric, fml.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- valuation ----------
def upsert_valuation(company_id, model_type, fair_value, scenario=None,
                     valuation_date=None, upside=None, assumption_json=None,
                     model_version="intelligence-v1"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO valuation (company_id, model_type, valuation_date, scenario,
                                   fair_value, upside, assumption_json, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (company_id, model_type, _to_date(valuation_date), scenario,
              fair_value, upside,
              json.dumps(assumption_json, ensure_ascii=False) if assumption_json else None,
              model_version))
        return cur.lastrowid


def get_valuations(company_id=None, symbol=None, model_type=None, scenario=None):
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
        if model_type:
            sql += " AND v.model_type=%s" if params else " WHERE v.model_type=%s"
            params.append(model_type)
        if scenario:
            sql += " AND v.scenario=%s" if params else " WHERE v.scenario=%s"
            params.append(scenario)
        sql += " ORDER BY v.valuation_date DESC, v.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- source / source_document / event / data_quality ----------
def upsert_source(name, source_type="api", provider=None, base_url=None,
                  reliability_score=0.5):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM source WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("""
            INSERT INTO source (source_type, provider, name, base_url, reliability_score)
            VALUES (%s, %s, %s, %s, %s)
        """, (source_type, provider, name, base_url, reliability_score))
        return cur.lastrowid


def insert_source_document(source_id, title, url=None, published_at=None,
                           document_type=None, content_hash=None, raw_path=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO source_document (source_id, title, url, published_at,
                                         document_type, content_hash, raw_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (source_id, title, url, published_at, document_type, content_hash, raw_path))
        return cur.lastrowid


def insert_event(event_type, title, event_date=None, company_id=None, industry_id=None,
                 impact_direction=None, impact_score=None, description=None,
                 source_document_id=None, status="active"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO event (event_type, title, event_date, company_id, industry_id,
                               impact_direction, impact_score, description,
                               source_document_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (event_type, title, event_date, company_id, industry_id,
              impact_direction, impact_score, description, source_document_id, status))
        return cur.lastrowid


def get_events(event_type=None, company_id=None, industry_id=None, hours=168, limit=50):
    with get_conn() as conn, conn.cursor() as cur:
        sql = "SELECT * FROM event WHERE event_date >= NOW() - INTERVAL %s HOUR"
        params = [hours]
        if event_type:
            sql += " AND event_type=%s"
            params.append(event_type)
        if company_id:
            sql += " AND company_id=%s"
            params.append(company_id)
        if industry_id:
            sql += " AND industry_id=%s"
            params.append(industry_id)
        sql += " ORDER BY event_date DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()


def log_quality(source_id, entity_type, entity_id, check_name, status, score=None, detail=None):
    """数据质量日志（第 24 节：freshness/consistency/outlier/lineage）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO data_quality_log (source_id, entity_type, entity_id, check_name,
                                          status, score, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (source_id, entity_type, entity_id, check_name, status, score, detail))
        return cur.lastrowid
