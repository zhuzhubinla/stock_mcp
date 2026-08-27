"""Validator：数据校验（Detailed Technical Design 第 16 节）
校验数值范围、日期合法性、必填字段、异常值；失败记入 data_quality_log。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")


def validate_required(record, required_fields):
    """必填字段校验：返回缺失字段列表"""
    missing = [f for f in required_fields if record.get(f) in (None, "")]
    return {"valid": not missing, "missing": missing}


def validate_range(value, lo=None, hi=None, name="value"):
    """数值范围校验：越界返回 False"""
    if value is None:
        return {"valid": True, "reason": None}
    v = float(value)
    if lo is not None and v < lo:
        return {"valid": False, "reason": f"{name}={v} 低于下限 {lo}"}
    if hi is not None and v > hi:
        return {"valid": False, "reason": f"{name}={v} 高于上限 {hi}"}
    return {"valid": True, "reason": None}


def validate_date(date_str):
    """日期合法性校验"""
    try:
        datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return {"valid": True, "reason": None}
    except (ValueError, TypeError):
        return {"valid": False, "reason": f"非法日期: {date_str}"}


def validate_outlier(value, series, sigma=3.0):
    """异常值检测：偏离均值超过 N 个标准差标记为异常"""
    if value is None or len(series) < 3:
        return {"valid": True, "reason": None}
    import statistics
    vals = [float(x) for x in series if x is not None]
    if len(vals) < 3:
        return {"valid": True, "reason": None}
    mean = statistics.mean(vals)
    stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
    if stdev == 0:
        return {"valid": True, "reason": None}
    z = abs(float(value) - mean) / stdev
    if z > sigma:
        return {"valid": False, "reason": f"异常值 z={z:.2f} > {sigma}（均值{mean:.2f}）"}
    return {"valid": True, "reason": None}


def run_validations(record, rules):
    """批量校验：rules = [('required', [fields]), ('range', 'field', lo, hi), ...]
    返回 (ok, failures)；可选择性写入 data_quality_log。
    """
    failures = []
    for rule in rules:
        kind = rule[0]
        if kind == "required":
            r = validate_required(record, rule[1])
            if not r["valid"]:
                failures.append({"check": "required", "detail": f"缺字段: {r['missing']}"})
        elif kind == "range":
            r = validate_range(record.get(rule[1]), rule[2] if len(rule) > 2 else None,
                               rule[3] if len(rule) > 3 else None, name=rule[1])
            if not r["valid"]:
                failures.append({"check": "range", "detail": r["reason"]})
        elif kind == "date":
            r = validate_date(record.get(rule[1]))
            if not r["valid"]:
                failures.append({"check": "date", "detail": r["reason"]})
    return {"valid": not failures, "failures": failures}
