"""Macro 仓储层：Phase 7 Macro→Industry Transmission Engine 全部数据访问
表：macro_factor / macro_industry_exposure / macro_transmission_edge /
    industry_transmission_event / industry_macro_score /
    macro_factor_signal / macro_regime
依据《Phase 7 设计文档》§14 字段级设计（2026-09-03 落地）。
"""
import sys
import json
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn


# ================= macro_factor =================
def list_factors(category=None):
    with get_conn() as conn, conn.cursor() as cur:
        sql = "SELECT * FROM macro_factor"
        if category:
            sql += f" WHERE category=%s"
            cur.execute(sql, (category,))
        else:
            cur.execute(sql)
        return cur.fetchall()


def get_factor(code=None, factor_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        if factor_id:
            cur.execute("SELECT * FROM macro_factor WHERE id=%s", (factor_id,))
        elif code:
            cur.execute("SELECT * FROM macro_factor WHERE code=%s", (code,))
        else:
            return None
        return cur.fetchone()


# ================= macro_industry_exposure =================
def get_exposures(industry_id=None, factor_id=None, regime="ALL", horizon="ALL",
                  model_version=None, as_of=None):
    """敏感性列表。regime/horizon='ALL' 取基础值；指定时取覆盖值（无覆盖则回退基础值由调用方处理）。"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT e.*, f.code AS factor_code, f.name AS factor_name,
                   i.code AS industry_code, i.name AS industry_name
            FROM macro_industry_exposure e
            JOIN macro_factor f ON f.id = e.factor_id
            JOIN industry i ON i.id = e.industry_id
            WHERE 1=1
        """
        params = []
        if industry_id:
            sql += " AND e.industry_id=%s"; params.append(industry_id)
        if factor_id:
            sql += " AND e.factor_id=%s"; params.append(factor_id)
        if regime and regime != "ALL":
            sql += " AND e.regime IN ('ALL', %s)"; params.append(regime)
        if horizon and horizon != "ALL":
            sql += " AND e.horizon IN ('ALL', %s)"; params.append(horizon)
        if model_version:
            sql += " AND e.model_version=%s"; params.append(model_version)
        if as_of:
            sql += " AND (e.valid_from IS NULL OR e.valid_from<=%s) AND (e.valid_to IS NULL OR e.valid_to>=%s)"
            params += [as_of, as_of]
        sql += " ORDER BY e.industry_id, e.factor_id"
        cur.execute(sql, params)
        return cur.fetchall()


def upsert_exposure(factor_id, industry_id, sensitivity, confidence=0.5,
                    source="expert", model_version="v1", regime="ALL",
                    horizon="ALL", valid_from=None, valid_to=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM macro_industry_exposure
            WHERE factor_id=%s AND industry_id=%s AND model_version=%s
              AND regime=%s AND horizon=%s
        """, (factor_id, industry_id, model_version, regime, horizon))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE macro_industry_exposure
                SET sensitivity=%s, confidence=%s, source=%s,
                    valid_from=COALESCE(%s, valid_from), valid_to=%s
                WHERE id=%s
            """, (sensitivity, confidence, source, valid_from, valid_to, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO macro_industry_exposure
              (factor_id, industry_id, sensitivity, confidence, source, model_version,
               regime, horizon, valid_from, valid_to)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (factor_id, industry_id, sensitivity, confidence, source, model_version,
              regime, horizon, valid_from, valid_to))
        return cur.lastrowid


# ================= macro_transmission_edge =================
def get_edges(source_type=None, target_type=None, model_version=None):
    """有效传导边（含节点名称，便于路径解释）"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT e.*,
                   CASE WHEN e.source_type='macro_factor' THEN sf.code ELSE NULL END AS source_code,
                   CASE WHEN e.source_type='macro_factor' THEN sf.name ELSE NULL END AS source_name,
                   CASE WHEN e.target_type='macro_factor' THEN tf.code ELSE NULL END AS target_code,
                   CASE WHEN e.target_type='macro_factor' THEN tf.name ELSE NULL END AS target_name
            FROM macro_transmission_edge e
            LEFT JOIN macro_factor sf ON sf.id = e.source_id AND e.source_type='macro_factor'
            LEFT JOIN macro_factor tf ON tf.id = e.target_id AND e.target_type='macro_factor'
            WHERE (e.valid_from IS NULL OR e.valid_from<=CURDATE())
              AND (e.valid_to IS NULL OR e.valid_to>=CURDATE())
        """
        params = []
        if source_type:
            sql += " AND e.source_type=%s"; params.append(source_type)
        if target_type:
            sql += " AND e.target_type=%s"; params.append(target_type)
        if model_version:
            sql += " AND e.model_version=%s"; params.append(model_version)
        sql += " ORDER BY e.id"
        cur.execute(sql, params)
        return cur.fetchall()


# ================= macro_factor_signal =================
def upsert_factor_signal(factor_id, signal_value, z_score=None, indicator_code=None,
                         indicator_value=None, as_of=None, source="fred",
                         model_version="v1", detail=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM macro_factor_signal
            WHERE factor_id=%s AND as_of=%s AND source=%s AND model_version=%s
        """, (factor_id, as_of, source, model_version))
        row = cur.fetchone()
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        if row:
            cur.execute("""
                UPDATE macro_factor_signal
                SET signal_value=%s, z_score=%s, indicator_code=%s, indicator_value=%s,
                    detail=%s
                WHERE id=%s
            """, (signal_value, z_score, indicator_code, indicator_value,
                  detail_json, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO macro_factor_signal
              (factor_id, signal_value, z_score, indicator_code, indicator_value,
               as_of, source, model_version, detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (factor_id, signal_value, z_score, indicator_code, indicator_value,
              as_of, source, model_version, detail_json))
        return cur.lastrowid


def get_latest_signals(source="fred", model_version="v1"):
    """每个因子最新一条信号"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.*, f.code AS factor_code, f.name AS factor_name
            FROM macro_factor_signal s
            JOIN macro_factor f ON f.id = s.factor_id
            WHERE s.id IN (
                SELECT MAX(s2.id) FROM macro_factor_signal s2
                WHERE s2.source=%s AND s2.model_version=%s
                GROUP BY s2.factor_id
            )
        """, (source, model_version))
        return cur.fetchall()


# ================= macro_regime =================
def upsert_macro_regime(regime, growth_yoy, inflation_yoy, growth_rising,
                        inflation_rising, confidence, detail=None):
    with get_conn() as conn, conn.cursor() as cur:
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        cur.execute("""
            INSERT INTO macro_regime
              (regime, growth_yoy, inflation_yoy, growth_rising, inflation_rising,
               confidence, detail, snapshot_time)
            VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (regime, growth_yoy, inflation_yoy, int(growth_rising),
              int(inflation_rising), confidence, detail_json))
        return cur.lastrowid


def get_latest_macro_regime():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM macro_regime ORDER BY snapshot_time DESC, id DESC LIMIT 1")
        row = cur.fetchone()
        if row and row.get("detail"):
            try:
                row["detail"] = json.loads(row["detail"])
            except Exception:
                pass
        return row


# ================= industry_transmission_event =================
def save_transmission_event(event_id, industry_id, impact_score, direction,
                            confidence, explanation=None, event_source="macro_signal"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_transmission_event
              (event_id, event_source, industry_id, impact_score, direction,
               confidence, explanation)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (event_id, event_source, industry_id, impact_score, direction,
              confidence, explanation))
        return cur.lastrowid


def get_transmission_events(event_id=None, industry_id=None, limit=20):
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT t.*, i.code AS industry_code, i.name AS industry_name
            FROM industry_transmission_event t
            JOIN industry i ON i.id = t.industry_id
            WHERE 1=1
        """
        params = []
        if event_id is not None:
            sql += " AND t.event_id=%s"; params.append(event_id)
        if industry_id:
            sql += " AND t.industry_id=%s"; params.append(industry_id)
        sql += " ORDER BY t.id DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()


# ================= industry_macro_score =================
def upsert_industry_macro_score(industry_id, horizon, regime, score,
                                expected_return, confidence, model_version="v1",
                                detail=None, score_date=None):
    from datetime import datetime
    sd = score_date or datetime.now().replace(second=0, microsecond=0)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM industry_macro_score
            WHERE industry_id=%s AND score_date=%s AND horizon=%s AND regime=%s AND model_version=%s
        """, (industry_id, sd, horizon, regime, model_version))
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE industry_macro_score
                SET score=%s, expected_return=%s, confidence=%s, detail=%s
                WHERE id=%s
            """, (score, expected_return, confidence, detail_json, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO industry_macro_score
              (industry_id, score_date, horizon, regime, score, expected_return,
               confidence, model_version, detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (industry_id, sd, horizon, regime, score, expected_return,
              confidence, model_version, detail_json))
        return cur.lastrowid


def get_latest_scores(industry_id=None, horizon=None, limit=50):
    """每个行业每个 horizon 最新一条分数"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT s.*, i.code AS industry_code, i.name AS industry_name
            FROM industry_macro_score s
            JOIN industry i ON i.id = s.industry_id
            WHERE s.id IN (
                SELECT MAX(s2.id) FROM industry_macro_score s2
                GROUP BY s2.industry_id, s2.horizon
            )
        """
        params = []
        if industry_id:
            sql += " AND s.industry_id=%s"; params.append(industry_id)
        if horizon:
            sql += " AND s.horizon=%s"; params.append(horizon)
        sql += " ORDER BY s.horizon, i.id LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        for r in rows:
            if r.get("detail"):
                try:
                    r["detail"] = json.loads(r["detail"])
                except Exception:
                    pass
        return rows


def get_score_history(industry_id=None, horizon="1d", limit=30):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.*, i.code AS industry_code
            FROM industry_macro_score s
            JOIN industry i ON i.id = s.industry_id
            WHERE s.horizon=%s AND (%s IS NULL OR s.industry_id=%s)
            ORDER BY s.score_date DESC LIMIT %s
        """, (horizon, industry_id, industry_id, limit))
        rows = cur.fetchall()
        for r in rows:
            if r.get("detail"):
                try:
                    r["detail"] = json.loads(r["detail"])
                except Exception:
                    pass
        return rows
