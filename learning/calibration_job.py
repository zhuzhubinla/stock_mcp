"""Continuous Calibration Job（Phase 8 定时任务）
- 回填 forward return → 计算 IC → 更新动态权重（版本化）
- 建议频率：每日一次（在收盘数据齐备后），或每周一次
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from learning.online_calibration import run_calibration, backfill_forward_returns


def run_continuous_calibration(horizon_days=20):
    """执行一轮持续校准（幂等：无新样本时自动跳过）"""
    print(f"[calibration] {datetime.now():%Y-%m-%d %H:%M} 开始校准 horizon={horizon_days}d")
    try:
        result = run_calibration(horizon_days=horizon_days)
        print(f"[calibration] status={result.get('status')} reason={result.get('reason', '')}")
        if result.get("status") == "ok":
            print(f"[calibration] ic_mean={result['ic_mean']} "
                  f"weights: {result['weight_version_from']} -> {result['weight_version_to']}")
            for ch in result.get("changed", []):
                print(f"  {ch['component']}: ic={ch['ic']:.3f} "
                      f"{ch['old']:.3f} -> {ch['new']:.3f}")
        return result
    except Exception as e:
        print(f"[calibration] 失败: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def run_backfill_all():
    """回填 5d + 20d forward return"""
    out = {}
    for h in (5, 20):
        out[h] = backfill_forward_returns(horizon_days=h)
    print(f"[calibration] backfill: {out}")
    return out


if __name__ == "__main__":
    run_backfill_all()
    run_continuous_calibration(horizon_days=5)
    run_continuous_calibration(horizon_days=20)
