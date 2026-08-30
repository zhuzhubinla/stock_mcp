"""Phase 8 Online Learning / Continuous Calibration（设计文档第 26 节）

核心思路（按文档 Phase 8）：
  1. 每个 score_snapshot 记录成分分 + 权重版本 + 时间
  2. 回填 forward return（5d/20d 实际收益）→ 得到 (成分分, 收益) 样本
  3. 计算每个成分的信息系数 IC（Spearman 相关：成分分 vs 未来收益）
  4. 在线更新动态权重：IC 高的成分加权，IC 低/负的成分降权
     new_weight ∝ old_weight × (1 + learning_rate × IC)
  5. 版本化：每次校准产生新权重版本，旧版本保留可回测
  6. 安全阀：权重上下限、样本量门槛、IC 置信度门槛，防过拟合

设计文档 25.2 对应验证指标：
  - IC（信息系数）→ 成分预测能力
  - Calibration → 置信度校准
  - Ablation → 各成分增量价值（通过 IC 与权重变化体现）
"""
import sys
import math
import json
from datetime import datetime, timedelta

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn, get_stock, get_prices
from scoring.weight_engine import get_weight_config, save_weight_config, COMPONENTS

MIN_SAMPLES = 5          # 最少样本数（不足则跳过校准）
MIN_ABS_IC = 0.15        # IC 绝对值门槛（低于此不调整）
WEIGHT_MIN, WEIGHT_MAX = 0.05, 0.60
LEARNING_RATE = 0.20     # 在线学习率（单次调整幅度上限）
HORIZON_DEFAULT = 20     # 默认前瞻窗口（交易日）


# ---------- 工具 ----------
def _spearman(xs, ys):
    """Spearman 秩相关（numpy 实现），范围 [-1, 1]"""
    import numpy as np
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    n = len(xs)
    d = rx - ry
    denom = n * (n * n - 1)  # Spearman 分母 n(n²-1)，公式 1 - 6Σd²/denom
    if denom == 0:
        return None
    return float(1.0 - 6.0 * np.sum(d * d) / denom)


def _forward_return(symbol, snapshot_time, horizon_days):
    """计算 snapshot 时间点之后的 horizon_days 交易日实际收益
    取 snapshot 当天收盘价 → 之后第 horizon 天的收盘价
    """
    bars = get_prices(symbol, days=400)
    if len(bars) < 2:
        return None
    # 找 snapshot 当天及之后第一个交易日
    start_idx = None
    for i, b in enumerate(bars):
        if b["timestamp"].date() >= snapshot_time.date():
            start_idx = i
            break
    if start_idx is None:
        return None
    end_idx = start_idx + horizon_days
    if end_idx >= len(bars):
        return None
    p0 = float(bars[start_idx]["close"])
    p1 = float(bars[end_idx]["close"])
    if not p0:
        return None
    return (p1 - p0) / p0


def backfill_forward_returns(horizon_days=HORIZON_DEFAULT, limit=200):
    """为历史 snapshot 回填 forward_return（幂等：已有值跳过）"""
    col = f"forward_return_{horizon_days}d"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT ss.id, ss.stock_id, ss.snapshot_time, st.symbol
            FROM score_snapshot ss JOIN stock st ON st.id = ss.stock_id
            WHERE ss.{col} IS NULL ORDER BY ss.snapshot_time ASC LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
    filled = 0
    for r in rows:
        ret = _forward_return(r["symbol"], r["snapshot_time"], horizon_days)
        if ret is None:
            continue
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE score_snapshot SET {col}=%s WHERE id=%s",
                        (round(ret, 6), r["id"]))
        filled += 1
    return {"horizon_days": horizon_days, "scanned": len(rows), "filled": filled}


# ---------- IC 计算 ----------
def compute_component_ics(horizon_days=HORIZON_DEFAULT, min_samples=MIN_SAMPLES):
    """对每个成分计算 IC：(成分分, forward_return) 的 Spearman 相关"""
    col = f"forward_return_{horizon_days}d"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT sc.component, sc.score, ss.{col} AS fwd
            FROM score_component sc
            JOIN score_snapshot ss ON ss.id = sc.snapshot_id
            WHERE ss.{col} IS NOT NULL AND sc.score IS NOT NULL
        """)
        rows = cur.fetchall()
    by_comp = {}
    for r in rows:
        fwd = r["fwd"]
        if fwd is None:
            continue
        by_comp.setdefault(r["component"], []).append((float(r["score"]), float(fwd)))
    ics = {}
    for comp, pairs in by_comp.items():
        if len(pairs) < min_samples:
            ics[comp] = {"ic": None, "samples": len(pairs), "note": "样本不足"}
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        ic = _spearman(xs, ys)
        ics[comp] = {"ic": round(ic, 4) if ic is not None else None,
                     "samples": len(pairs),
                     "note": "ok" if ic is not None else "IC 计算失败"}
    return ics


# ---------- 权重在线更新 ----------
def _update_weights(old_weights, ics, lr=LEARNING_RATE, min_abs_ic=MIN_ABS_IC):
    """new_weight = old_weight × (1 + lr × IC)，归一化 + 限幅
    注意：相对权重，整体缩放会被归一化抵消，因此只保留 IC 差异带来的相对变化。"""
    new_weights = {}
    changed = []
    for comp in COMPONENTS:
        old = old_weights.get(comp, 0.1)
        info = ics.get(comp, {})
        ic = info.get("ic")
        if ic is None or abs(ic) < min_abs_ic:
            new_weights[comp] = old
            continue
        # 在线学习步长：IC 每高 0.1，权重乘 (1+lr)；上限 lr 封顶
        step = max(-lr, min(lr, lr * ic * 5))
        new_weights[comp] = old * (1.0 + step)
        changed.append({"component": comp, "ic": ic, "old": old,
                        "new": old * (1.0 + step)})
    # 限幅 + 归一化
    for comp in new_weights:
        new_weights[comp] = max(WEIGHT_MIN, min(WEIGHT_MAX, new_weights[comp]))
    total = sum(new_weights.values())
    new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}
    return new_weights, changed


def _weights_changed(old_weights, new_weights, eps=0.005):
    """新旧权重是否有实际差异（防空版本号空转）"""
    for comp in COMPONENTS:
        if abs(new_weights.get(comp, 0) - old_weights.get(comp, 0)) > eps:
            return True
    return False


def run_calibration(horizon_days=HORIZON_DEFAULT, persist=True, lr=LEARNING_RATE,
                    min_abs_ic=MIN_ABS_IC):
    """执行一轮校准：
    1. 回填 forward return
    2. 计算各成分 IC
    3. 更新权重 → 新版本落库
    4. 记录 calibration_run + calibration_component
    """
    # 1. 回填
    bf = backfill_forward_returns(horizon_days)
    # 2. IC
    ics = compute_component_ics(horizon_days)
    ok_ics = {k: v for k, v in ics.items() if v.get("ic") is not None}
    if not ok_ics:
        return {"status": "skipped", "reason": "无可校准样本（等待回填 forward return）",
                "backfill": bf, "ics": ics}

    # 3. 权重更新
    old_cfg = get_weight_config()
    old_weights = {k: v for k, v in old_cfg["weights"].items() if k in COMPONENTS}
    new_weights, changed = _update_weights(old_weights, ics, lr=lr, min_abs_ic=min_abs_ic)
    ic_mean = sum(v["ic"] for v in ok_ics.values()) / len(ok_ics)
    old_version = old_cfg["version"]

    # 权重无实际变化 → 记录 run 但不产生新版本（防空转）
    if not _weights_changed(old_weights, new_weights):
        run_id = _record_run("ic_weight", horizon_days, ok_ics, ic_mean,
                             old_version, old_version, "no_change", bf, lr,
                             old_weights, new_weights, ics)
        return {"status": "no_change", "run_id": run_id,
                "reason": "IC 未达调权门槛，权重保持不变",
                "ic_mean": round(ic_mean, 4), "ics": ics,
                "backfill": bf, "weight_version": old_version}

    if not persist:
        return {"status": "dry_run", "old_weights": old_weights,
                "new_weights": new_weights, "changed": changed, "ics": ics,
                "ic_mean": round(ic_mean, 4)}

    # 4. 新版本落库（v1 → v2 → v3 ...）
    seq = 0
    for ch in [c for c in old_version.split("-") if c.startswith("v")]:
        try:
            seq = max(seq, int(ch[1:]))
        except ValueError:
            pass
    new_version = f"intelligence-v{seq + 1}"
    save_weight_config(new_version, new_weights, regime="all", active=1)
    # 旧版本取消 active
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE score_weight_config SET active=0 WHERE version=%s",
                    (old_version,))

    # 5. 记录 calibration_run
    run_id = _record_run("ic_weight", horizon_days, ok_ics, ic_mean,
                         old_version, new_version, "ok", bf, lr,
                         old_weights, new_weights, ics)

    return {
        "status": "ok",
        "run_id": run_id,
        "horizon_days": horizon_days,
        "ic_mean": round(ic_mean, 4),
        "weight_version_from": old_version,
        "weight_version_to": new_version,
        "changed": changed,
        "ics": ics,
        "backfill": bf,
    }


def _record_run(run_type, horizon_days, ok_ics, ic_mean, ver_from, ver_to,
                status, bf, lr, old_weights, new_weights, ics):
    """写入 calibration_run + calibration_component，返回 run_id"""
    run_id = None
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO calibration_run (run_type, horizon_days, sample_count, ic_mean,
                                         weight_version_from, weight_version_to, status,
                                         detail, run_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (run_type, horizon_days,
              sum(v["samples"] for v in ok_ics.values()), round(ic_mean, 4),
              ver_from, ver_to, status,
              json.dumps({"backfill": bf, "learning_rate": lr}, ensure_ascii=False),
              datetime.now()))
        run_id = cur.lastrowid
        for comp, info in ics.items():
            ic = info.get("ic")
            old_w = old_weights.get(comp)
            new_w = new_weights.get(comp)
            accepted = 1 if (ic is not None and abs(ic) >= MIN_ABS_IC) else 0
            cur.execute("""
                INSERT INTO calibration_component (run_id, component, ic, old_weight, new_weight, accepted)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (run_id, comp, ic, old_w, new_w, accepted))
    return run_id


def get_calibration_history(limit=10):
    """校准历史"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT cr.*, 
              (SELECT COUNT(*) FROM calibration_component cc WHERE cc.run_id=cr.id) AS comp_count
            FROM calibration_run cr ORDER BY cr.run_time DESC LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        for r in rows:
            if isinstance(r.get("detail"), str):
                try:
                    r["detail"] = json.loads(r["detail"])
                except Exception:
                    pass
            cur.execute("""
                SELECT component, ic, old_weight, new_weight, accepted
                FROM calibration_component WHERE run_id=%s ORDER BY ic DESC
            """, (r["id"],))
            r["components"] = cur.fetchall()
    return rows


if __name__ == "__main__":
    import json
    print(json.dumps(run_calibration(horizon_days=5), ensure_ascii=False, indent=1, default=str))
