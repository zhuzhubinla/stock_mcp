"""industry_macro_update：Phase 7 每日宏观信号/行业分刷新
- 信号依赖 FRED 宏观序列（由 08:50 industry_sync 先同步）
- 09:55 计算因子信号 + 宏观 regime + 1d/1w/1m 行业宏观分
"""
import sys
sys.path.append("/home/admin/stock_agent")

from domain.industry.scoring import refresh_macro_scores
from domain.macro.regime import detect_macro_regime


def run_industry_macro_update():
    """计算并落库：因子信号 → macro regime → 行业宏观分（1d/1w/1m）"""
    detect_macro_regime(persist=True)
    res = refresh_macro_scores(horizons=("1d", "1w", "1m"), persist=True)
    counts = {h: len(imp) for h, imp in res["horizons"].items()}
    print(f"[industry_macro_update] regime={res['regime']} "
          f"conf={res['regime_confidence']:.2f} horizons={counts}")
    return {"regime": res["regime"],
            "regime_confidence": res["regime_confidence"],
            "industries_per_horizon": counts,
            "computed_at": res["computed_at"]}


if __name__ == "__main__":
    print(run_industry_macro_update())
