"""Signal Conflict Engine（设计文档第 12 节）

系统必须显式识别冲突，而不是简单把正负信号相加。
典型冲突：
  Fundamental +++ vs Market ---  → Fundamental/Market Divergence
  Financial +++ vs Prediction --- → Financial/Prediction Divergence
  News +++ vs Long-term Industry --- → News/Industry Divergence
记录冲突来源和严重程度，传递给 Risk 和 LLM Explanation。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

# 冲突对配置：哪些域组合值得关注
CONFLICT_PAIRS = [
    ("fundamental", "market", "Fundamental/Market Divergence"),
    ("financial", "prediction", "Financial/Prediction Divergence"),
    ("news", "industry", "News vs Long-term Industry"),
    ("fundamental", "valuation", "Growth vs Valuation"),
    ("market", "prediction", "Market vs Prediction"),
]

SEVERITY_THRESHOLD = 0.4  # 冲突强度超过该值才记录


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))


def detect_conflicts(component_scores):
    """component_scores: {"fundamental": 0~1, "market": 0~1, ...}（0~100 也行）
    返回冲突列表：[{domains, severity, description}]
    """
    if not component_scores:
        return []
    conflicts = []
    # 归一化到 0~1（若传入 0~100）
    norm = {}
    for k, v in component_scores.items():
        if v is None:
            continue
        norm[k] = float(v) / 100.0 if abs(float(v)) > 1.5 else float(v)
    for a, b, label in CONFLICT_PAIRS:
        va = norm.get(a)
        vb = norm.get(b)
        if va is None or vb is None:
            continue
        # 方向相反且至少一方偏离中性 0.15 以上
        if (va - 0.5) * (vb - 0.5) < 0 and max(abs(va - 0.5), abs(vb - 0.5)) > 0.15:
            severity = _clamp(abs(va - vb) / 1.0)
            if severity >= SEVERITY_THRESHOLD:
                conflicts.append({
                    "domains": f"{a},{b}",
                    "severity": round(severity, 4),
                    "description": f"{label}: {a}={va:.2f} vs {b}={vb:.2f}",
                })
    conflicts.sort(key=lambda c: c["severity"], reverse=True)
    return conflicts


def save_conflicts(symbol, conflicts):
    """冲突持久化到 signal_conflict 表"""
    if not conflicts:
        return 0
    from data.repositories.mysql_db import get_stock
    stock = get_stock(symbol.upper())
    if not stock:
        return 0
    stock_id = stock["id"]
    with get_conn() as conn, conn.cursor() as cur:
        for c in conflicts[:5]:
            cur.execute("""
                INSERT INTO signal_conflict (stock_id, domains, severity, description)
                VALUES (%s, %s, %s, %s)
            """, (stock_id, c["domains"], c["severity"], c["description"][:255]))
    return len(conflicts[:5])


def get_conflicts(symbol, limit=20):
    """读取股票最近的冲突记录"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT sc.domains, sc.severity, sc.description, sc.created_at
            FROM signal_conflict sc JOIN stock st ON st.id = sc.stock_id
            WHERE st.symbol=%s ORDER BY sc.created_at DESC LIMIT %s
        """, (symbol.upper(), limit))
        return cur.fetchall()


if __name__ == "__main__":
    scores = {"fundamental": 85, "market": 30, "news": 70, "industry": 60, "prediction": 45}
    print(detect_conflicts(scores))
