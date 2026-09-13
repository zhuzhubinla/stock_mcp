"""Macro Signal：宏观原始序列 → Surprise/Z-Score → 因子信号 [-1,+1]
（设计文档 §4 数据流 + Python 架构 macro/signal.py）

防泄露：所有统计只使用 as_of 之前的序列点；序列存的是发布口径原始值。
"""
import sys
import math
from datetime import date

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo, factor_repo
from domain.macro.factor import SIGNAL_SPECS, MODEL_VERSION


def _load_series(indicator_code, as_of=None, max_rows=61):
    """升序取序列 [(period_date, float)]，只含 <= as_of 的点"""
    rows = factor_repo.get_indicators(indicator_code=indicator_code)
    pts = []
    for r in rows:
        p = r.get("period")
        if p is None or r.get("value") is None:
            continue
        p_date = p if isinstance(p, date) else date.fromisoformat(str(p)[:10])
        if as_of and p_date > as_of:
            continue
        pts.append((p_date, float(r["value"])))
    pts.sort(key=lambda x: x[0])
    return pts


def _stats(vals):
    n = len(vals)
    if n < 2:
        return None, None
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return mean, math.sqrt(var)


def _mom_yoy_z(pts):
    """月频：12 期同比变化序列，用滚动窗口（近 12 个同比）算 z"""
    if len(pts) < 13:
        return None
    yoy = [(pts[i][0], (pts[i][1] / pts[i - 12][1] - 1) * 100)
           for i in range(12, len(pts))]
    if len(yoy) < 6:
        return None
    last_val = yoy[-1][1]
    hist = [v for _, v in yoy[-13:-1]]
    mean, std = _stats(hist)
    if mean is None or std is None or std < 1e-9:
        return 0.0
    return (last_val - mean) / std


def _level_z(pts):
    """日频：水平值 vs 前 60 个点均值/标准差的 z"""
    if len(pts) < 15:
        return None
    last_val = pts[-1][1]
    hist = [v for _, v in pts[-61:-1]]
    mean, std = _stats(hist)
    if mean is None or std is None or std < 1e-9:
        return 0.0
    return (last_val - mean) / std


def compute_factor_signals(as_of=None, persist=True):
    """计算全部因子信号。返回 {factor_code: {signal, z, indicator_code,
    indicator_value, as_of, detail}}；无数据源因子不返回（调用方视为中性）。"""
    as_of = as_of or date.today()
    out = {}
    for code, specs in SIGNAL_SPECS.items():
        if not specs:
            continue
        zs, used = [], []
        detail = {}
        for ind_code, weight, mode in specs:
            pts = _load_series(ind_code, as_of=as_of)
            if not pts:
                continue
            z = _mom_yoy_z(pts) if mode == "mom_yoy" else _level_z(pts)
            if z is None:
                continue
            zs.append(weight * z)
            used.append(ind_code)
            detail[ind_code] = {"weight": weight, "z": round(z, 4),
                                "latest": pts[-1][1],
                                "latest_period": str(pts[-1][0])}
        if not used:
            continue
        # 按使用到源的实际权重做加权归一（未取到数据的源不摊薄信号）
        w_sum = sum(abs(w) for ind_code, w, _ in specs if ind_code in used)
        z_agg = sum(zs) / w_sum if w_sum else 0.0
        signal = math.tanh(z_agg / 2.0)
        factor = macro_repo.get_factor(code=code)
        data_asof = max(detail[u]["latest_period"] for u in used)
        row = {
            "signal": round(signal, 6), "z": round(z_agg, 6),
            "indicator_code": used[0],
            "indicator_value": detail[used[0]]["latest"],
            "as_of": str(data_asof), "detail": detail,
        }
        if persist and factor:
            macro_repo.upsert_factor_signal(
                factor["id"], signal, z_score=z_agg, indicator_code=used[0],
                indicator_value=detail[used[0]]["latest"],
                as_of=str(data_asof), source="fred",
                model_version=MODEL_VERSION, detail=detail)
        out[code] = row
    return out


def latest_signals_dict():
    """DB 中最新信号 {factor_code: {signal, confidence 固定 0.7}}"""
    rows = macro_repo.get_latest_signals()
    return {r["factor_code"]: {"signal": float(r["signal_value"]),
                               "z": float(r["z_score"]) if r["z_score"] is not None else 0.0,
                               "as_of": str(r["as_of"]),
                               "indicator_code": r["indicator_code"],
                               "indicator_value": float(r["indicator_value"])
                               if r["indicator_value"] is not None else None}
            for r in rows}
