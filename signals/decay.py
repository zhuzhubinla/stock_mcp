"""Time Decay：信号时间衰减（设计文档第 10 节）

Signal(t) = Signal(0) × exp(-λt)

信号类型与建议有效期（可配置，版本化以保证回测可复现）：
  Breaking News   1-3 天    λ ≈ ln(2)/1.5d
  Earnings/Guidance 30-90 天 λ ≈ ln(2)/45d
  Industry Trend  3-12 个月  λ ≈ ln(2)/180d
  Macro           1-6 个月   λ ≈ ln(2)/90d
  Prediction      按事件到期日动态计算

半衰期 half_life_days = ln(2) / λ  →  λ = ln(2) / half_life_days
"""
import sys
import math
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

DEFAULT_HALF_LIFE = {
    "news": 1.5,          # 天
    "earnings": 45.0,
    "guidance": 45.0,
    "industry": 180.0,
    "macro": 90.0,
    "prediction": 30.0,
    "default": 30.0,
}

# 版本号：衰减参数变更时必须递增，保证历史回测可复现
DECAY_VERSION = "v1"


def half_life(signal_type, config=None):
    cfg = config or DEFAULT_HALF_LIFE
    return cfg.get(signal_type, cfg["default"])


def lambda_from_half_life(hl_days):
    return math.log(2) / hl_days if hl_days > 0 else 1.0


def decay_factor(signal_type, age_hours, config=None):
    """衰减系数 = exp(-λt)，t 以天为单位"""
    hl = half_life(signal_type, config)
    lam = lambda_from_half_life(hl)
    t_days = age_hours / 24.0
    return math.exp(-lam * t_days)


def apply_decay(strength, signal_type, observed_at, config=None, now=None):
    """对信号强度施加时间衰减"""
    if strength is None:
        return None, 1.0
    now = now or datetime.now()
    if observed_at is None:
        return float(strength), 1.0
    age = (now - observed_at).total_seconds() / 3600.0
    if age < 0:
        age = 0.0
    factor = decay_factor(signal_type, age, config)
    return float(strength) * factor, factor


def effective_horizon(signal_type, config=None):
    """有效时间（天）：衰减到 10% 以下视为失效 ≈ 3.32×half_life"""
    hl = half_life(signal_type, config)
    return round(hl * math.log(10) / math.log(2), 1)


if __name__ == "__main__":
    print("news half_life:", half_life("news"), "天, 有效期:", effective_horizon("news"), "天")
    print("earnings 有效期:", effective_horizon("earnings"), "天")
    print("news 24h 衰减:", round(decay_factor("news", 24), 3))
    print("earnings 30d 衰减:", round(decay_factor("earnings", 30 * 24), 3))
    print("industry 180d 衰减:", round(decay_factor("industry", 180 * 24), 3))
