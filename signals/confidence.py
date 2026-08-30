"""Confidence Engine（设计文档第 11 节）

Confidence = Source Quality × Signal Agreement × Data Freshness
             × Sample/Liquidity Quality × Model Stability

Score 表示方向/强度，Confidence 表示证据质量与一致性，二者独立存储。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")


def _clamp(v, lo=0.0, hi=1.0):
    if v is None:
        return 0.0
    return max(lo, min(hi, float(v)))


# 来源质量基准（0~1）
SOURCE_QUALITY = {
    "sec": 0.95, "finnhub": 0.85, "nasdaq": 0.8, "yfinance": 0.75,
    "fred": 0.9, "polymarket": 0.7, "kalshi": 0.7, "metaculus": 0.6,
    "manifold": 0.5, "news_finnhub": 0.7, "llm": 0.6, "rule": 0.5,
    "default": 0.6,
}


def source_quality(source):
    return SOURCE_QUALITY.get(source, SOURCE_QUALITY["default"])


def agreement_factor(signals):
    """信号一致性：同向比例。全部同向=1，五五开=0.3"""
    if not signals:
        return 0.5
    pos = sum(1 for s in signals if (s or 0) > 0.05)
    neg = sum(1 for s in signals if (s or 0) < -0.05)
    neu = len(signals) - pos - neg
    total = len(signals)
    if neu >= total * 0.6:
        return 0.3  # 大部分中性 = 低信息
    dominant = max(pos, neg)
    return _clamp(0.3 + 0.7 * (dominant / total))


def freshness_factor(ages_hours, max_age_hours=24 * 30):
    """数据新鲜度：最近一条数据的年龄 → 0~1"""
    if not ages_hours:
        return 0.5
    age = min(ages_hours)
    return _clamp(1.0 - age / max_age_hours)


def sample_quality(n_samples, min_samples=3):
    """样本量质量：数据点越少置信越低"""
    if n_samples is None:
        return 0.5
    return _clamp(n_samples / min_samples)


def model_stability(model_version=None, stable_versions=None):
    """模型稳定性：同一版本使用次数越多越稳（简化：有版本号即 0.8）"""
    if model_version:
        return 0.8
    return 0.5


def compute_confidence(sources=None, signals=None, ages_hours=None,
                       n_samples=None, model_version=None, weights=None):
    """综合置信度（乘法模型，各因子独立）"""
    w = weights or {
        "source": 0.25, "agreement": 0.25, "freshness": 0.2,
        "sample": 0.15, "stability": 0.15,
    }
    f_source = sum(source_quality(s) for s in (sources or ["default"])) / max(len(sources or [1]), 1)
    f_agree = agreement_factor(signals)
    f_fresh = freshness_factor(ages_hours)
    f_sample = sample_quality(n_samples)
    f_stable = model_stability(model_version)

    confidence = (w["source"] * f_source + w["agreement"] * f_agree
                  + w["freshness"] * f_fresh + w["sample"] * f_sample
                  + w["stability"] * f_stable)
    return round(_clamp(confidence), 4), {
        "source": round(f_source, 3), "agreement": round(f_agree, 3),
        "freshness": round(f_fresh, 3), "sample": round(f_sample, 3),
        "stability": round(f_stable, 3),
    }


if __name__ == "__main__":
    c, factors = compute_confidence(
        sources=["sec", "finnhub"], signals=[0.6, 0.5, -0.1],
        ages_hours=[2, 5, 30], n_samples=10, model_version="v1")
    print("confidence:", c, factors)
