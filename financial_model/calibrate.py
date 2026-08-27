"""Driver Calibrator：统计回归校准驱动系数（方法③）
用真实历史数据拟合弹性：公司营收增速 ~ 行业指标增速 的回归系数 = 实际驱动系数。
数据：
- 公司侧：SEC XBRL 年度营收（10-K FY 行，所有公司均有）
- 指标侧：industry_indicator 全序列（按 indicator_code 查，FRED 月度/种子年度）
算法：按年聚合 → 同比增速 → 线性回归（numpy lstsq）
样本 ≥ 4 个对齐年份才更新系数，否则保留经验值并降置信度。
"""
import sys
import json
import numpy as np
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories import factor_repo, mysql_db as db
from data.collectors.sec_financials import _ticker_to_cik

import requests

SEC_HEADERS = {"User-Agent": "stock-agent admin@example.com"}

# 收入概念回退链（各公司 GAAP 标签不统一）
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax1",
    "RevenueFromContractWithCustomerExcludingAssessedTax2",
]

# 代理指标映射：种子指标 code → FRED 真实序列 code（历史充足，同语义）
CALIBRATION_PROXIES = {
    "ai_chip_shipment": "semiconductor_production_index",
    "ai_glass_shipment": "electronics_retail_sales",
    "dram_contract_price": "semiconductor_ppi",
    "cloud_capex": "industrial_production",
}


def get_annual_revenue(symbol):
    """SEC companyfacts 年度营收：{ 'YYYY' : revenue }（10-K FY 行，多概念回退）"""
    cik = _ticker_to_cik().get(symbol.upper())
    if not cik:
        return {}
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    gaap = r.json().get("facts", {}).get("us-gaap", {})
    # 取回退链中第一个有 10-K FY 数据的概念
    for concept in REVENUE_CONCEPTS:
        node = gaap.get(concept)
        if not node:
            continue
        out = {}
        for unit_rows in node.get("units", {}).values():
            for row in unit_rows:
                if row.get("form") != "10-K" or row.get("fp") != "FY":
                    continue
                end = row.get("end", "")
                year = end[:4] if len(end) >= 4 else None
                if not year or not row.get("val"):
                    continue
                if year not in out or row["val"] > out[year]:
                    out[year] = row["val"]
        if out:
            return out
    return {}


def get_indicator_by_code(indicator_id, symbol=None):
    """按驱动绑定的 indicator_id 反查 code，再取该指标全序列：{ 'YYYY' : 年均值 }
    历史不足时自动用代理指标（CALIBRATION_PROXIES → FRED 真实序列）。
    """
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT indicator_code, industry_id FROM industry_indicator WHERE id=%s",
                    (indicator_id,))
        row = cur.fetchone()
        if not row:
            return {}, None
        code, industry_id = row["indicator_code"], row["industry_id"]
        cur.execute("""
            SELECT period, value FROM industry_indicator
            WHERE industry_id=%s AND indicator_code=%s AND value IS NOT NULL
            ORDER BY period
        """, (industry_id, code))
        rows = cur.fetchall()
    by_year = {}
    for r in rows:
        y = str(r["period"])[:4]
        if y.isdigit():
            by_year.setdefault(y, []).append(float(r["value"]))
    series = {y: sum(v) / len(v) for y, v in by_year.items()}

    # 历史不足 → 用代理 FRED 序列（跨行业查 code）
    proxy_code = CALIBRATION_PROXIES.get(code)
    if len(series) < 4 and proxy_code:
        proxy = _get_series_by_code(proxy_code)
        if len(proxy) >= len(series):
            return proxy, f"{code}→{proxy_code}(代理)"
    return series, code


def _get_series_by_code(code):
    """按 indicator_code 全局取序列（不限行业）"""
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT period, value FROM industry_indicator
            WHERE indicator_code=%s AND value IS NOT NULL ORDER BY period
        """, (code,))
        rows = cur.fetchall()
    by_year = {}
    for r in rows:
        y = str(r["period"])[:4]
        if y.isdigit():
            by_year.setdefault(y, []).append(float(r["value"]))
    return {y: sum(v) / len(v) for y, v in by_year.items()}


def _yoy_years(series):
    """{year: value} → [(year, yoy_pct)]"""
    out = []
    for y in sorted(series):
        if str(int(y) - 1) in series and series[str(int(y) - 1)]:
            out.append((y, (series[y] - series[str(int(y) - 1)]) / series[str(int(y) - 1)] * 100.0))
    return out


def calibrate_driver(driver_id, min_points=4, persist=True):
    """回归单个驱动：公司营收 YoY ~ 指标 YoY → 系数 = 回归斜率
    安全阀：R² 过低 / 系数方向与 impact_direction 矛盾 / 系数超出合理范围 → 拒绝写入。
    """
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT fd.*, c.stock_symbol FROM financial_driver fd
            JOIN company c ON c.id = fd.company_id WHERE fd.id=%s
        """, (driver_id,))
        d = cur.fetchone()
    if not d:
        return {"driver_id": driver_id, "error": "驱动不存在"}
    symbol = d["stock_symbol"]
    indicator_id = d.get("indicator_id")
    if not indicator_id:
        return {"driver_id": driver_id, "symbol": symbol, "error": "无绑定指标，无法校准"}

    # 1) 公司年度营收（SEC 10-K）
    try:
        rev = get_annual_revenue(symbol)
    except Exception as e:
        return {"driver_id": driver_id, "symbol": symbol, "error": f"SEC 营收获取失败: {e}"}
    if len(rev) < 3:
        return {"driver_id": driver_id, "symbol": symbol,
                "error": f"SEC 年度营收样本不足({len(rev)}年)"}

    # 2) 指标全序列（按 code，历史不足自动用 FRED 代理）
    ind, code = get_indicator_by_code(indicator_id)
    if not ind or len(ind) < 3:
        return {"driver_id": driver_id, "symbol": symbol,
                "error": f"指标({code})历史样本不足({len(ind)}年)，保留经验系数"}

    # 3) 双方同比
    rev_yoy = dict(_yoy_years(rev))
    ind_yoy = dict(_yoy_years(ind))
    common = sorted(set(rev_yoy) & set(ind_yoy))
    if len(common) < min_points:
        return {"driver_id": driver_id, "symbol": symbol,
                "error": f"对齐样本不足({len(common)}年<{min_points})，保留经验系数"}

    X = np.array([ind_yoy[y] for y in common], dtype=float)
    Y = np.array([rev_yoy[y] for y in common], dtype=float)
    A = np.vstack([X, np.ones(len(X))]).T
    b, a = np.linalg.lstsq(A, Y, rcond=None)[0]
    y_pred = a + b * X
    ss_res = np.sum((Y - y_pred) ** 2)
    ss_tot = np.sum((Y - np.mean(Y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    new_coeff = round(float(b) / 100.0, 4)  # 增速%对增速% → 无量纲弹性
    expected_dir = 1 if d["impact_direction"] == "positive" else -1
    coeff_dir_ok = (new_coeff > 0) == (expected_dir > 0)
    coeff_range_ok = 0.05 <= abs(new_coeff) <= 3.0
    r2_ok = r2 >= 0.5

    if not (coeff_dir_ok and coeff_range_ok and r2_ok):
        reasons = []
        if not coeff_dir_ok:
            reasons.append(f"方向矛盾(期望{expected_dir:+}, 回归{new_coeff:+})")
        if not coeff_range_ok:
            reasons.append(f"系数超合理范围(0.05~3.0): {new_coeff}")
        if not r2_ok:
            reasons.append(f"R²={r2:.2f}<0.5")
        return {"driver_id": driver_id, "symbol": symbol, "driver": d["driver_name"],
                "metric": d["impact_metric"], "indicator": code,
                "years": common, "regression_slope": round(float(b), 4),
                "r2": round(float(r2), 4), "old_coefficient":
                float(d["impact_coefficient"]) if d["impact_coefficient"] is not None else None,
                "new_coefficient": new_coeff,
                "rejected": True, "reason": "; ".join(reasons)}

    confidence = round(min(0.95, max(0.3, r2)), 4)
    if persist:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE financial_driver
                SET impact_coefficient=%s, elasticity=%s, confidence=%s
                WHERE id=%s
            """, (new_coeff, round(abs(new_coeff) * 0.8, 4), confidence, driver_id))

    return {
        "driver_id": driver_id, "symbol": symbol, "driver": d["driver_name"],
        "metric": d["impact_metric"], "indicator": code,
        "years": common, "aligned_points": len(common),
        "regression_slope": round(float(b), 4), "r2": round(float(r2), 4),
        "old_coefficient": float(d["impact_coefficient"]) if d["impact_coefficient"] is not None else None,
        "new_coefficient": new_coeff, "confidence": confidence,
        "rejected": False,
    }


def calibrate_all(min_points=4, persist=True):
    """校准全部驱动"""
    rows = factor_repo.get_financial_drivers()
    ids = sorted({r["id"] for r in rows})
    results = []
    for did in ids:
        try:
            results.append(calibrate_driver(did, min_points=min_points, persist=persist))
        except Exception as e:
            results.append({"driver_id": did, "error": str(e)[:120]})
    updated = [r for r in results if "new_coefficient" in r]
    kept = [r for r in results if "error" in r]
    print(f"[calibrate] 更新 {len(updated)}/{len(results)}，样本不足保留 {len(kept)}")
    return {"results": results, "updated": len(updated), "kept": len(kept)}


if __name__ == "__main__":
    print(json.dumps(calibrate_all(), ensure_ascii=False, indent=1)[:3000])
