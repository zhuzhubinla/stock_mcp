"""数据质量检查（Detailed Technical Design 第 24 节）
Source Reliability / Data Confidence / Freshness / Consistency / Outlier / Lineage
检查结果写入 data_quality_log。
"""
import sys
from datetime import datetime, timedelta

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn
from data.repositories import forecast_repo


def check_freshness(entity_type, entity_id, last_updated, max_age_hours, source_id=None):
    """新鲜度：数据最后更新时间是否在窗口内"""
    if last_updated is None:
        status, score = "fail", 0.0
        detail = "无更新时间"
    else:
        age = (datetime.now() - last_updated).total_seconds() / 3600
        if age <= max_age_hours:
            status, score = "pass", max(0.0, 1.0 - age / max_age_hours)
            detail = f"age={age:.1f}h <= {max_age_hours}h"
        else:
            status, score = "fail", 0.0
            detail = f"age={age:.1f}h > {max_age_hours}h"
    forecast_repo.log_quality(source_id, entity_type, entity_id, "freshness",
                              status, score, detail)
    return {"check": "freshness", "status": status, "score": score, "detail": detail}


def check_consistency(entity_type, entity_id, value, expected, tolerance=0.01, source_id=None):
    """一致性：跨来源数值偏差是否在容差内"""
    if value is None or expected is None:
        status, score = "warn", 0.5
        detail = "缺少对照值"
    else:
        diff = abs(float(value) - float(expected)) / max(abs(float(expected)), 1e-9)
        if diff <= tolerance:
            status, score = "pass", 1.0 - diff
            detail = f"偏差 {diff:.4%} <= {tolerance:.2%}"
        else:
            status, score = "fail", 0.0
            detail = f"偏差 {diff:.4%} > {tolerance:.2%}"
    forecast_repo.log_quality(source_id, entity_type, entity_id, "consistency",
                              status, score, detail)
    return {"check": "consistency", "status": status, "score": score, "detail": detail}


def check_outlier(entity_type, entity_id, value, series, sigma=3.0, source_id=None):
    """异常值：偏离均值 N 个标准差"""
    from data.validators.base import validate_outlier
    r = validate_outlier(value, series, sigma=sigma)
    status = "pass" if r["valid"] else "fail"
    score = 1.0 if r["valid"] else 0.0
    forecast_repo.log_quality(source_id, entity_type, entity_id, "outlier",
                              status, score, r["reason"])
    return {"check": "outlier", "status": status, "score": score, "detail": r["reason"]}


def run_quality_scan(symbols=None):
    """对 watchlist 跑基础质量扫描（新鲜度 + 基本面异常值）"""
    from jobs.news_update import load_watchlist
    from data.adapters import stock_service
    symbols = symbols or load_watchlist()
    results = []
    for symbol in symbols:
        try:
            latest = stock_service.get_quote(symbol)
            ts = latest.get("time")
            last_updated = None
            if ts:
                try:
                    last_updated = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    last_updated = None
            results.append({"symbol": symbol, "check": "quote_freshness",
                            **check_freshness("stock", symbol, last_updated, 24)})
            # 基本面异常值
            metrics = stock_service.get_fundamentals(symbol).get("metrics", [])
            for m in metrics:
                if m["metric"] in ("pe", "pb", "netMargin", "grossMargin"):
                    val = float(m["value"])
                    if abs(val) > 500:
                        results.append({"symbol": symbol, "check": f"outlier_{m['metric']}",
                                        "detail": f"{val:.1f} 异常"})
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
    print(f"[quality] 扫描完成 {len(results)} 条检查")
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    run_quality_scan()
