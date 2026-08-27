"""Factor 仓储层：industry_factor / industry_indicator / supply_demand / financial_driver
依据《Detailed Technical Design》第 9-10 节字段级设计。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn


# ---------- industry_factor ----------
def upsert_industry_factor(industry_id, name, factor_type="demand", impact_direction="positive",
                           description=None, importance=None, unit=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry_factor WHERE industry_id=%s AND name=%s",
                    (industry_id, name))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE industry_factor SET factor_type=%s, impact_direction=%s,
                  description=COALESCE(%s, description), importance=COALESCE(%s, importance),
                  unit=COALESCE(%s, unit), source_id=COALESCE(%s, source_id)
                WHERE id=%s
            """, (factor_type, impact_direction, description, importance, unit,
                  source_id, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO industry_factor (industry_id, name, factor_type, impact_direction,
                                         description, importance, unit, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (industry_id, name, factor_type, impact_direction, description,
              importance, unit, source_id))
        return cur.lastrowid


def get_industry_factors(industry_id=None, factor_type=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT f.*, i.name AS industry_name, i.code AS industry_code
            FROM industry_factor f JOIN industry i ON i.id = f.industry_id
        """
        params = []
        if industry_id:
            sql += " WHERE f.industry_id=%s"
            params.append(industry_id)
        if factor_type:
            sql += " AND f.factor_type=%s" if params else " WHERE f.factor_type=%s"
            params.append(factor_type)
        sql += " ORDER BY f.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- industry_indicator ----------
def upsert_indicator(industry_id, indicator_code, indicator_name, value, unit=None,
                     period=None, frequency="yearly", source_id=None):
    """period: 'YYYY' / 'YYYY-MM-DD' / 'YYYY-MM' 均转 DATE"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_indicator (industry_id, indicator_code, indicator_name,
                                            value, unit, period, frequency, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE value=VALUES(value), unit=COALESCE(VALUES(unit), unit),
              indicator_name=VALUES(indicator_name),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (industry_id, indicator_code, indicator_name, value, unit,
              _to_date(period), frequency, source_id))
        return cur.lastrowid


def _to_date(period):
    """'2024' → '2024-01-01'；'2024Q1' → '2024-01-01'；'2025-06' → '2025-06-01'；DATE 直接返回"""
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


def get_indicators(industry_id=None, indicator_code=None, symbol=None, indicator_name=None):
    """行业指标；symbol 时经 industry_company 反查该公司所属行业的指标"""
    with get_conn() as conn, conn.cursor() as cur:
        if symbol:
            sql = """
                SELECT ind.*, i.name AS industry_name, i.code AS industry_code
                FROM industry_indicator ind
                JOIN industry i ON i.id = ind.industry_id
                JOIN industry_company ic ON ic.industry_id = i.id
                JOIN company c ON c.id = ic.company_id
                WHERE c.stock_symbol=%s
            """
            params = [symbol]
        else:
            sql = """
                SELECT ind.*, i.name AS industry_name, i.code AS industry_code
                FROM industry_indicator ind
                JOIN industry i ON i.id = ind.industry_id
            """
            params = []
            if industry_id:
                sql += " WHERE ind.industry_id=%s"
                params.append(industry_id)
        if indicator_code:
            sql += " AND ind.indicator_code=%s" if params else " WHERE ind.indicator_code=%s"
            params.append(indicator_code)
        if indicator_name:
            sql += " AND ind.indicator_name=%s" if params else " WHERE ind.indicator_name=%s"
            params.append(indicator_name)
        sql += " ORDER BY ind.period DESC, ind.id"
        cur.execute(sql, params)
        return cur.fetchall()


def get_indicator_series(industry_id, indicator_code, limit=24):
    """某指标的时间序列（按 period 升序）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM industry_indicator
            WHERE industry_id=%s AND indicator_code=%s
            ORDER BY period ASC LIMIT %s
        """, (industry_id, indicator_code, limit))
        rows = cur.fetchall()
    by_period = {str(r["period"]): r for r in rows}
    return [by_period[k] for k in sorted(by_period.keys())]


# ---------- supply_demand ----------
def upsert_supply_demand(industry_id, period, capacity=None, production=None, demand=None,
                         inventory=None, utilization_rate=None, supply_demand_gap=None,
                         unit=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO supply_demand (industry_id, period, capacity, production, demand,
                                       inventory, utilization_rate, supply_demand_gap, unit, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              capacity=COALESCE(VALUES(capacity), capacity),
              production=COALESCE(VALUES(production), production),
              demand=COALESCE(VALUES(demand), demand),
              inventory=COALESCE(VALUES(inventory), inventory),
              utilization_rate=COALESCE(VALUES(utilization_rate), utilization_rate),
              supply_demand_gap=COALESCE(VALUES(supply_demand_gap), supply_demand_gap),
              unit=COALESCE(VALUES(unit), unit),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (industry_id, _to_date(period), capacity, production, demand, inventory,
              utilization_rate, supply_demand_gap, unit, source_id))
        return cur.lastrowid


def get_supply_demand(industry_id=None, period=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT sd.*, i.name AS industry_name FROM supply_demand sd
            JOIN industry i ON i.id = sd.industry_id
        """
        params = []
        if industry_id:
            sql += " WHERE sd.industry_id=%s"
            params.append(industry_id)
        if period:
            sql += " AND sd.period=%s" if params else " WHERE sd.period=%s"
            params.append(_to_date(period))
        sql += " ORDER BY sd.period DESC"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- financial_driver ----------
def upsert_financial_driver(company_id, driver_name, impact_metric="revenue",
                            impact_direction="positive", business_segment_id=None,
                            factor_id=None, indicator_id=None, impact_coefficient=None,
                            elasticity=None, base_value=None, forecast_value=None,
                            confidence=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO financial_driver (company_id, business_segment_id, factor_id,
                                          indicator_id, driver_name, impact_metric,
                                          impact_direction, impact_coefficient, elasticity,
                                          base_value, forecast_value, confidence, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              factor_id=COALESCE(VALUES(factor_id), factor_id),
              impact_direction=VALUES(impact_direction),
              impact_coefficient=COALESCE(VALUES(impact_coefficient), impact_coefficient),
              elasticity=COALESCE(VALUES(elasticity), elasticity),
              base_value=COALESCE(VALUES(base_value), base_value),
              forecast_value=COALESCE(VALUES(forecast_value), forecast_value),
              confidence=COALESCE(VALUES(confidence), confidence),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (company_id, business_segment_id, factor_id, indicator_id, driver_name,
              impact_metric, impact_direction, impact_coefficient, elasticity,
              base_value, forecast_value, confidence, source_id))
        return cur.lastrowid


def get_financial_drivers(company_id=None, symbol=None, impact_metric=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT fd.*, c.name AS company_name, c.stock_symbol,
                   bs.name AS segment_name, i.name AS industry_name,
                   ind.indicator_code, ind.indicator_name AS source_indicator
            FROM financial_driver fd
            JOIN company c ON c.id = fd.company_id
            LEFT JOIN business_segment bs ON bs.id = fd.business_segment_id
            LEFT JOIN industry i ON i.id = bs.industry_id
            LEFT JOIN industry_indicator ind ON ind.id = fd.indicator_id
        """
        params = []
        if symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE fd.company_id=%s"
            params.append(company_id)
        if impact_metric:
            sql += " AND fd.impact_metric=%s" if params else " WHERE fd.impact_metric=%s"
            params.append(impact_metric)
        sql += " ORDER BY fd.id"
        cur.execute(sql, params)
        return cur.fetchall()


def get_driver_by_indicator(indicator_id):
    """指标 → 关联的财务驱动（Factor-First 用）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT fd.*, c.name AS company_name, c.stock_symbol,
                   bs.name AS segment_name
            FROM financial_driver fd
            JOIN company c ON c.id = fd.company_id
            LEFT JOIN business_segment bs ON bs.id = fd.business_segment_id
            WHERE fd.indicator_id=%s
        """, (indicator_id,))
        return cur.fetchall()
