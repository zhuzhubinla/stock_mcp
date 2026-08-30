"""Weight Engine：动态权重配置与版本化（设计文档第 13 节）

基础权重（文档 13.1）：
  Fundamental 30% / Precondition 25% / Market 15% / News 15% / Prediction 15%

动态调整（13.2/13.3 示例）：
  - 财报前：Fundamental 35% / Expectation 20% / Prediction 20% / News 10% / Market 10% / Macro 5%
  - 宏观事件前：Macro 30% / Prediction 25% / Market 15% / Fundamental 15% / News 10% / Industry 5%

Phase 8 Online Learning 将基于历史 IC 自动更新权重（见 learning/online_calibration.py），
所有权重配置版本化保存于 score_weight_config 表。
"""
import sys
import json
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

DEFAULT_VERSION = "intelligence-v1"
COMPONENTS = ["fundamental", "precondition", "market", "news", "prediction"]

# 默认基础权重（文档 13.1）
DEFAULT_WEIGHTS = {
    "fundamental": 0.30,
    "precondition": 0.25,
    "market": 0.15,
    "news": 0.15,
    "prediction": 0.15,
}

# 财报前权重模板（文档 13.2）
EARNINGS_SEASON_WEIGHTS = {
    "fundamental": 0.35,
    "precondition": 0.20,
    "market": 0.10,
    "news": 0.10,
    "prediction": 0.20,
    "macro": 0.05,
}

# 宏观事件前权重模板（文档 13.3）
MACRO_EVENT_WEIGHTS = {
    "fundamental": 0.15,
    "precondition": 0.10,
    "market": 0.15,
    "news": 0.10,
    "prediction": 0.25,
    "macro": 0.30,
}


def _clamp_weights(weights):
    """归一化 + 下限保护"""
    total = sum(max(v, 0.05) for v in weights.values())
    return {k: round(max(v, 0.05) / total, 6) for k, v in weights.items()}


def save_weight_config(version, weights, regime="all", active=1):
    """保存权重配置（版本化）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO score_weight_config (version, weights, regime, active, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              weights=VALUES(weights), regime=VALUES(regime),
              active=VALUES(active), created_at=VALUES(created_at)
        """, (version, json.dumps(_clamp_weights(weights), ensure_ascii=False),
              regime, active, datetime.now()))
    return version


def get_weight_config(version=None):
    """读取权重配置：指定版本或最新 active"""
    with get_conn() as conn, conn.cursor() as cur:
        if version:
            cur.execute("SELECT * FROM score_weight_config WHERE version=%s", (version,))
        else:
            cur.execute("""
                SELECT * FROM score_weight_config WHERE active=1
                ORDER BY id DESC LIMIT 1
            """)
        row = cur.fetchone()
    if not row:
        # 默认配置落库
        save_weight_config(DEFAULT_VERSION, DEFAULT_WEIGHTS, active=1)
        return {"version": DEFAULT_VERSION, "weights": DEFAULT_WEIGHTS,
                "regime": "all", "source": "default"}
    if isinstance(row.get("weights"), str):
        row["weights"] = json.loads(row["weights"])
    row["source"] = "db"
    return row


def select_weights(context_vector=None, upcoming_event=None):
    """动态选择权重：
    1. 优先取库内最新 active 版本（Phase 8 在线学习更新后的权重）
    2. 有 upcoming_event 时套用财报/宏观模板（简化：叠加在最新权重上再归一化）
    """
    cfg = get_weight_config()
    weights = dict(cfg["weights"])

    if upcoming_event == "earnings":
        merged = dict(weights)
        merged.update(EARNINGS_SEASON_WEIGHTS)
        weights = _clamp_weights(merged)
        weights["_template"] = "earnings_season"
    elif upcoming_event == "macro":
        merged = dict(weights)
        merged.update(MACRO_EVENT_WEIGHTS)
        weights = _clamp_weights(merged)
        weights["_template"] = "macro_event"

    # 确保五大成分都在
    for c in COMPONENTS:
        weights.setdefault(c, DEFAULT_WEIGHTS[c])
    return weights, cfg["version"]


def list_weight_versions():
    """所有权重版本历史"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT version, weights, regime, active, created_at
            FROM score_weight_config ORDER BY id DESC LIMIT 50
        """)
        rows = cur.fetchall()
    for r in rows:
        if isinstance(r.get("weights"), str):
            try:
                r["weights"] = json.loads(r["weights"])
            except Exception:
                pass
    return rows


if __name__ == "__main__":
    import json
    v = save_weight_config("intelligence-v1", DEFAULT_WEIGHTS, active=1)
    print("saved:", v)
    cfg = get_weight_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=1, default=str))
