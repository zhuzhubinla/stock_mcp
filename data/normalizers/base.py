"""Normalizer：代码、单位、日期、字段统一（Detailed Technical Design 第 16 节）
Collector 抓到原始数据后 → Normalizer 标准化，不进行主观分析。
"""
import sys
import re
from datetime import datetime

sys.path.append("/home/admin/stock_agent")


def normalize_ticker(ticker):
    """证券代码统一：去空格、大写、规范化交易所前缀"""
    if not ticker:
        return None
    t = str(ticker).strip().upper()
    # 美股：去掉 .US 后缀
    if t.endswith(".US"):
        t = t[:-3]
    # A股：600519.SH / 000001.SZ / 688608.SH 保持
    return t


def normalize_period(period):
    """period 统一为 DATE 字符串：'2024'→'2024-01-01'、'2024Q1'→'2024-01-01'、'2025-06'→'2025-06-01'"""
    if period is None:
        return None
    if isinstance(period, datetime):
        return period.strftime("%Y-%m-%d")
    s = str(period).strip()
    if len(s) == 4 and s.isdigit():
        return f"{s}-01-01"
    if len(s) == 6 and s[4] == "Q":
        q = {"1": "01", "2": "04", "3": "07", "4": "10"}.get(s[5], "01")
        return f"{s[:4]}-{q}-01"
    if len(s) == 7 and s[4] == "-":
        return f"{s}-01"
    if len(s) >= 10:
        return s[:10]
    return s


def normalize_number(value):
    """数值统一：去 $/%/,/空格，转 float；无法解析返回 None"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in ("", "N/A", "NA", "-", "--"):
        return None
    s = s.replace("$", "").replace("%", "").replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_unit(unit):
    """单位统一：百万/十亿/百分比 → 标准单位"""
    if not unit:
        return None
    u = str(unit).strip().lower()
    mapping = {
        "mn": "million", "million": "million", "百万": "million",
        "bn": "billion", "billion": "billion", "十亿": "billion",
        "%": "percent", "pct": "percent", "百分比": "percent",
        "usd": "usd", "美元": "usd", "元": "cny",
    }
    return mapping.get(u, u)


def normalize_fields(record, field_map):
    """字段名统一：record 的原始字段 → 规范字段"""
    return {canonical: record.get(src) for src, canonical in field_map.items()}
