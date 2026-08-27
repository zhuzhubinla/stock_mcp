"""Graph 仓储层：company / industry / business_segment / chain / relationship / industry_company
对应文档第 5 节核心数据模型。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.repositories.mysql_db import get_conn


# ---------- company ----------
def upsert_company(stock_symbol, name, legal_name=None, country=None, exchange=None,
                   listed=1, sector=None, description=None, source_id=None):
    """按名称 upsert 公司主体，返回 company_id"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM company WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE company SET stock_symbol=COALESCE(%s, stock_symbol),
                  legal_name=COALESCE(%s, legal_name), country=COALESCE(%s, country),
                  exchange=COALESCE(%s, exchange), listed=COALESCE(%s, listed),
                  sector=COALESCE(%s, sector), description=COALESCE(%s, description)
                WHERE id=%s
            """, (stock_symbol, legal_name, country, exchange, listed, sector, description, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO company (stock_symbol, name, legal_name, country, exchange,
                                 listed, sector, description, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (stock_symbol, name, legal_name, country, exchange, listed, sector, description, source_id))
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
def upsert_industry(code, name, level=1, parent_id=None, description=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry WHERE code=%s", (code,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE industry SET name=%s, level=%s, parent_id=COALESCE(%s, parent_id),
                  description=COALESCE(%s, description) WHERE id=%s
            """, (name, level, parent_id, description, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO industry (code, name, level, parent_id, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (code, name, level, parent_id, description))
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
                            revenue_share=None, is_primary=0):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM business_segment WHERE company_id=%s AND name=%s",
                    (company_id, name))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE business_segment SET description=COALESCE(%s, description),
                  industry_id=COALESCE(%s, industry_id),
                  revenue_share=COALESCE(%s, revenue_share), is_primary=%s WHERE id=%s
            """, (description, industry_id, revenue_share, is_primary, row["id"]))
            return row["id"]
        cur.execute("""
            INSERT INTO business_segment (company_id, name, description, industry_id,
                                          revenue_share, is_primary)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (company_id, name, description, industry_id, revenue_share, is_primary))
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
def upsert_chain(name, description=None, category=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry_chain WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO industry_chain (name, description, category) VALUES (%s,%s,%s)",
                    (name, description, category))
        return cur.lastrowid


def upsert_chain_node(chain_id, name, node_type=None, description=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM industry_chain_node WHERE chain_id=%s AND name=%s",
                    (chain_id, name))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("""
            INSERT INTO industry_chain_node (chain_id, name, node_type, description)
            VALUES (%s, %s, %s, %s)
        """, (chain_id, name, node_type, description))
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
        cur.execute("SELECT * FROM industry_chain_node WHERE chain_id=%s ORDER BY id", (chain_id,))
        nodes = cur.fetchall()
        cur.execute("SELECT * FROM industry_chain_edge WHERE chain_id=%s ORDER BY id", (chain_id,))
        edges = cur.fetchall()
    return {"nodes": nodes, "edges": edges}


# ---------- company_relationship ----------
def upsert_relationship(company_id, related_company_id, relation_type,
                        importance=None, confidence=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_relationship (company_id, related_company_id, relation_type,
                                              importance, confidence, source_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              importance=COALESCE(VALUES(importance), importance),
              confidence=COALESCE(VALUES(confidence), confidence),
              source_id=COALESCE(VALUES(source_id), source_id)
        """, (company_id, related_company_id, relation_type, importance, confidence, source_id))


def get_relationships(company_id=None, symbol=None, relation_type=None):
    """公司关系（双向展开：A→B 和 B→A 都返回，方向用 relation_type 表达）"""
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
            sql += " AND cr.relation_type=%s" if params else " WHERE cr.relation_type=%s"
            params.append(relation_type)
        sql += " ORDER BY cr.importance DESC"
        cur.execute(sql, params)
        return cur.fetchall()


# ---------- industry_company ----------
def upsert_industry_company(industry_id, company_id, exposure=1.0, role=None, source_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO industry_company (industry_id, company_id, exposure, role, source_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              exposure=VALUES(exposure), role=VALUES(role), source_id=COALESCE(VALUES(source_id), source_id)
        """, (industry_id, company_id, exposure, role, source_id))


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
            sql += " AND ic.exposure >= %s"
            params.append(min_exposure)
        sql += " ORDER BY ic.exposure DESC, ic.id"
        cur.execute(sql, params)
        return cur.fetchall()
