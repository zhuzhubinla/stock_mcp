"""Graph 仓储层：company / industry / business_segment / chain / relationship / industry_company
依据《Detailed Technical Design》第 6-8 节字段级设计。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn


# ---------- company ----------
def upsert_company(stock_symbol=None, name=None, name_en=None, country=None,
                   company_type="public", description=None, website=None,
                   status="active", source_id=None):
    """按名称 upsert 公司主体，返回 company_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM company WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE company SET name_en=COALESCE(%s, name_en),
                  country=COALESCE(%s, country), company_type=COALESCE(%s, company_type),
                  description=COALESCE(%s, description), website=COALESCE(%s, website),
                  status=COALESCE(%s, status),
                  stock_symbol=COALESCE(%s, stock_symbol)
                WHERE id=%s
            """, (name_en, country, company_type, description, website, status,
                  stock_symbol, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO company (name, name_en, country, company_type, description,
                                 website, status, stock_symbol)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, name_en, country, company_type, description, website, status,
              stock_symbol))
        return cur.lastrowid


def get_company(company_id=None, symbol=None, name=None):
    with get_conn() as conn, conn.cursor() as cur:
        if company_id:
            cur.execute("SELECT * FROM company WHERE id=%s", (company_id,))
        elif symbol:
            cur.execute("SELECT * FROM company WHERE stock_symbol=%s", (symbol,))
        elif name:
            cur.execute("SELECT * FROM company WHERE name=%s", (name,))
        else:
            return None
        return cur.fetchone()


def list_companies(symbols=None):
    with get_conn() as conn, conn.cursor() as cur:
        if symbols:
            fmt = ",".join(["%s"] * len(symbols))
            cur.execute(f"SELECT * FROM company WHERE stock_symbol IN ({fmt})", symbols)
        else:
            cur.execute("SELECT * FROM company ORDER BY id")
        return cur.fetchall()


# ---------- industry ----------
def upsert_industry(code, name, level=1, parent_id=None, description=None,
                    taxonomy="custom", name_en=None, status="active"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry WHERE taxonomy=%s AND code=%s",
                    (taxonomy, code))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE industry SET name=%s, name_en=COALESCE(%s, name_en), level=%s,
                  parent_id=COALESCE(%s, parent_id),
                  description=COALESCE(%s, description), status=%s WHERE id=%s
            """, (name, name_en, level, parent_id, description, status, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO industry (code, name, name_en, taxonomy, level, parent_id,
                                  description, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (code, name, name_en, taxonomy, level, parent_id, description, status))
        return cur.lastrowid


def get_industry(industry_id=None, code=None, name=None):
    with get_conn() as conn, conn.cursor() as cur:
        if industry_id:
            cur.execute("SELECT * FROM industry WHERE id=%s", (industry_id,))
        elif code:
            cur.execute("SELECT * FROM industry WHERE code=%s", (code,))
        elif name:
            cur.execute("SELECT * FROM industry WHERE name=%s", (name,))
        else:
            return None
        return cur.fetchone()


def list_industries(parent_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        if parent_id:
            cur.execute("SELECT * FROM industry WHERE parent_id=%s ORDER BY id", (parent_id,))
        else:
            cur.execute("SELECT * FROM industry ORDER BY id")
        return cur.fetchall()


# ---------- business_segment ----------
def upsert_business_segment(company_id, name, description=None, industry_id=None,
                            revenue_share=None, gross_margin=None, segment_type=None,
                            is_primary=0, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM business_segment WHERE company_id=%s AND name=%s",
                    (company_id, name))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE business_segment SET description=COALESCE(%s, description),
                  industry_id=COALESCE(%s, industry_id),
                  revenue_share=COALESCE(%s, revenue_share),
                  gross_margin=COALESCE(%s, gross_margin),
                  segment_type=COALESCE(%s, segment_type), is_primary=%s WHERE id=%s
            """, (description, industry_id, revenue_share, gross_margin,
                  segment_type, is_primary, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO business_segment (company_id, name, description, segment_type,
                                          revenue_share, gross_margin, industry_id, is_primary, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (company_id, name, description, segment_type, revenue_share,
              gross_margin, industry_id, is_primary, source_id))
        return cur.lastrowid


def get_business_segments(company_id=None, symbol=None):
    """取公司业务分拆（含行业名）。symbol 或 company_id 二选一"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT bs.*, i.name AS industry_name, i.code AS industry_code,
                   c.name AS company_name, c.stock_symbol
            FROM business_segment bs
            JOIN company c ON c.id = bs.company_id
            LEFT JOIN industry i ON i.id = bs.industry_id
        """
        if company_id:
            sql += " WHERE bs.company_id=%s ORDER BY bs.is_primary DESC, bs.id"
            cur.execute(sql, (company_id,))
        elif symbol:
            sql += " WHERE c.stock_symbol=%s ORDER BY bs.is_primary DESC, bs.id"
            cur.execute(sql, (symbol,))
        else:
            sql += " ORDER BY bs.id"
            cur.execute(sql)
        return cur.fetchall()


# ---------- industry_chain / node / edge ----------
def upsert_chain(name, description=None, industry_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry_chain WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO industry_chain (name, description, industry_id) VALUES (%s,%s,%s)",
                    (name, description, industry_id))
        return cur.lastrowid


def upsert_chain_node(chain_id, name, node_type=None, description=None,
                      parent_node_id=None, position=0):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry_chain_node WHERE chain_id=%s AND name=%s",
                    (chain_id, name))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("""
            INSERT INTO industry_chain_node (chain_id, name, node_type, description,
                                             parent_node_id, position)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (chain_id, name, node_type, description, parent_node_id, position))
        return cur.lastrowid


def upsert_chain_edge(chain_id, from_node_id, to_node_id, relation_type="supplies"):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT IGNORE INTO industry_chain_edge (chain_id, from_node_id, to_node_id, relation_type)
            VALUES (%s, %s, %s, %s)
        """, (chain_id, from_node_id, to_node_id, relation_type))


def get_chain(chain_id=None, name=None):
    with get_conn() as conn, conn.cursor() as cur:
        if chain_id:
            cur.execute("SELECT * FROM industry_chain WHERE id=%s", (chain_id,))
        elif name:
            cur.execute("SELECT * FROM industry_chain WHERE name=%s", (name,))
        else:
            return None
        return cur.fetchone()


def get_chain_graph(chain_id):
    """返回 {nodes: [...], edges: [...]}"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM industry_chain_node WHERE chain_id=%s ORDER BY position, id", (chain_id,))
        nodes = cur.fetchall()
        cur.execute("SELECT * FROM industry_chain_edge WHERE chain_id=%s ORDER BY id", (chain_id,))
        edges = cur.fetchall()
    return {"nodes": nodes, "edges": edges}


# ---------- company_relationship ----------
def upsert_relationship(company_id, related_company_id, relationship_type,
                        importance=None, confidence=None, description=None,
                        chain_node_id=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_relationship (company_id, related_company_id, relationship_type,
                                              importance, confidence, description,
                                              chain_node_id, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              importance=COALESCE(VALUES(importance), importance),
              confidence=COALESCE(VALUES(confidence), confidence),
              description=COALESCE(VALUES(description), description),
              chain_node_id=COALESCE(VALUES(chain_node_id), chain_node_id),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (company_id, related_company_id, relationship_type, importance,
              confidence, description, chain_node_id, source_id))


def get_relationships(company_id=None, symbol=None, relation_type=None):
    """公司关系（双向展开：A→B 和 B→A 都返回，方向用 relationship_type 表达）"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT cr.*, c1.name AS company_name, c1.stock_symbol,
                   c2.name AS related_name, c2.stock_symbol AS related_symbol
            FROM company_relationship cr
            JOIN company c1 ON c1.id = cr.company_id
            JOIN company c2 ON c2.id = cr.related_company_id
        """
        params = []
        if symbol:
            sql += " WHERE c1.stock_symbol=%s"
            params.append(symbol)
        elif company_id:
            sql += " WHERE cr.company_id=%s"
            params.append(company_id)
        if relation_type:
            sql += " AND cr.relationship_type=%s" if params else " WHERE cr.relationship_type=%s"
            params.append(relation_type)
        sql += " ORDER BY cr.importance DESC"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- industry_company（暴露度模型） ----------
def upsert_industry_company(industry_id, company_id, business_segment_id=None,
                            exposure_weight=1.0, revenue_exposure=None,
                            profit_exposure=None, confidence=None, role=None,
                            source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_company (industry_id, company_id, business_segment_id,
                                          exposure_weight, revenue_exposure, profit_exposure,
                                          confidence, role, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              exposure_weight=VALUES(exposure_weight),
              revenue_exposure=COALESCE(VALUES(revenue_exposure), revenue_exposure),
              profit_exposure=COALESCE(VALUES(profit_exposure), profit_exposure),
              confidence=COALESCE(VALUES(confidence), confidence),
              role=COALESCE(VALUES(role), role),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (industry_id, company_id, business_segment_id, exposure_weight,
              revenue_exposure, profit_exposure, confidence, role, source_id))


def get_industry_companies(industry_id=None, symbol=None, min_exposure=None):
    """行业→公司（含公司名/符号）；或按 symbol 反查公司所属行业"""
    with get_conn() as conn, conn.cursor() as cur:
        sql = """
            SELECT ic.*, i.name AS industry_name, i.code AS industry_code,
                   c.name AS company_name, c.stock_symbol
            FROM industry_company ic
            JOIN industry i ON i.id = ic.industry_id
            JOIN company c ON c.id = ic.company_id
        """
        params = []
        if industry_id:
            sql += " WHERE ic.industry_id=%s"
            params.append(industry_id)
        elif symbol:
            sql += " WHERE c.stock_symbol=%s"
            params.append(symbol)
        if min_exposure is not None:
            sql += " AND ic.exposure_weight >= %s"
            params.append(min_exposure)
        sql += " ORDER BY ic.exposure_weight DESC, ic.id"
        cur.execute(sql, params)
        return cur.fetchall()
