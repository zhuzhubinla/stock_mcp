"""Industry Exposure Manager（设计文档 §6 + Python 架构 industry/exposure.py）

EffectiveExposure = BaseSensitivity × RegimeMultiplier × EventMultiplier × HorizonMultiplier
Exposure 行按 (factor_id, industry_id, model_version, regime, horizon) 版本化存储，
regime/horizon='ALL' 为基础值；有特定覆盖时取最具体一行。
"""
import sys

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo
from domain.macro.regime import regime_factor_multiplier
from domain.macro.event import event_factor_multipliers
from domain.macro.factor import horizon_multiplier


def _pick_specific(rows):
    """按 (regime==特定, horizon==特定) 排序取最具体一行"""
    def spec(r):
        return (1 if r["regime"] != "ALL" else 0) + \
               (1 if r["horizon"] != "ALL" else 0)
    return max(rows, key=spec) if rows else None


class ExposureManager:
    def __init__(self, regime="neutral", horizon="1w", event_key=None, event_level="normal",
                 model_version=None, as_of=None):
        self.regime = regime or "neutral"
        self.horizon = horizon or "1w"
        self.event_muls = event_factor_multipliers(event_key, event_level)
        self.model_version = model_version
        self.as_of = as_of

    def effective_exposure(self, row):
        """单行 base exposure → effective（含三个修正乘数）"""
        f = row["factor_code"]
        return (float(row["sensitivity"])
                * regime_factor_multiplier(self.regime, f)
                * float(self.event_muls.get(f, 1.0))
                * horizon_multiplier(self.horizon, f))

    def load_effective(self, industry_id=None, factor_code=None):
        """返回 [{industry_id, industry_code, industry_name, factor_id, factor_code,
                  factor_name, base_sensitivity, regime, horizon, event_mult,
                  effective_sensitivity, confidence}]（按行业聚合去重）"""
        rows = macro_repo.get_exposures(
            industry_id=industry_id,
            model_version=self.model_version,
            as_of=self.as_of)
        if factor_code:
            rows = [r for r in rows if r["factor_code"] == factor_code]
        # 同 (industry, factor) 多版本行 → 取最具体
        merged = {}
        for r in rows:
            merged.setdefault((r["industry_id"], r["factor_code"]), []).append(r)
        out = []
        for (iid, fcode), group in merged.items():
            row = _pick_specific(group)
            base = float(row["sensitivity"])
            eff = (base
                   * regime_factor_multiplier(self.regime, fcode)
                   * float(self.event_muls.get(fcode, 1.0))
                   * horizon_multiplier(self.horizon, fcode))
            out.append({
                "industry_id": row["industry_id"],
                "industry_code": row["industry_code"],
                "industry_name": row["industry_name"],
                "factor_id": row["factor_id"],
                "factor_code": fcode,
                "factor_name": row["factor_name"],
                "base_sensitivity": round(base, 6),
                "regime": self.regime,
                "horizon": self.horizon,
                "event_multiplier": float(self.event_muls.get(fcode, 1.0)),
                "effective_sensitivity": round(eff, 6),
                "confidence": float(row["confidence"]),
            })
        return out

    def industry_exposure_map(self):
        """{industry_id: {factor_code: effective_sensitivity}}"""
        out = {}
        for row in self.load_effective():
            out.setdefault(row["industry_id"], {})[row["factor_code"]] = \
                row["effective_sensitivity"]
        return out
