"""Prediction Intelligence 定时任务（设计文档 8.3）
- 同步预测源（Kalshi 大陆可直连；Polymarket 需海外 VPS/代理）
- 计算多源共识 + 概率动量
- 执行 Prediction→Stock 映射（Knowledge Graph 传播）
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")


def run_prediction_sync(sources=None, limit=30, proxy=None):
    """完整预测管线：采集 → 共识 → 映射"""
    print(f"[prediction_sync] {datetime.now():%Y-%m-%d %H:%M} 开始")
    from data.collectors.prediction.collector import collect_all
    from domain.prediction.engine import compute_all_consensus
    from domain.prediction.mapper import map_all_events

    srcs = sources or ["kalshi"]  # Polymarket 需配置 proxy/海外 VPS 后加入
    collect = collect_all(limit=limit, proxy=proxy, sources=srcs)
    print(f"[prediction_sync] 采集: {[(r.get('source'), r.get('status')) for r in collect['results']]}")

    consensus = compute_all_consensus(persist=True)
    print(f"[prediction_sync] 共识: {len(consensus)} 个事件")

    mapped = map_all_events(persist=True)
    print(f"[prediction_sync] 映射: {mapped['mapped_events']}/{mapped['total_events']} 个事件 → 股票信号")

    return {
        "collect": collect,
        "consensus_count": len(consensus),
        "mapped": mapped,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_prediction_sync(), ensure_ascii=False, indent=1, default=str)[:1500])
