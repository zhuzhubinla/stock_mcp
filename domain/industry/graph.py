"""Transmission Graph（设计文档 §9 + Python 架构 industry/graph.py）

Node：macro_factor（V1 用因子作为节点；宏观指标可后续接入）
Edge：weight / direction / confidence / lag / source / model_version

PathScore = Signal × EdgeWeight×Direction × ... × Confidence × LagDecay
多跳带衰减（damping），避免过长路径产生虚假放大。
"""
import sys
import math

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo

# 每跳信号衰减（经验值：0.6，抑制多跳放大）
HOP_DAMPING = 0.6
# 时滞衰减：λ=0.15/天，按 lag 中点天数衰减
LAG_DECAY_LAMBDA = 0.15
MAX_DEPTH = 2


def _lag_decay(lag_min, lag_max):
    mid_days = ((lag_min or 0) + (lag_max or lag_min or 0)) / 2.0 / 1440.0
    return math.exp(-LAG_DECAY_LAMBDA * mid_days)


class TransmissionGraph:
    """因子级传导图：加载 macro_transmission_edge，做多跳传播"""

    def __init__(self, model_version=None):
        self.edges = macro_repo.get_edges(model_version=model_version)
        # adjacency: source_factor_code -> [(target_code, weight, direction, conf, decay)]
        self.adj = {}
        self.paths = []  # 解释用：完整路径样本
        for e in self.edges:
            if e["source_type"] != "macro_factor" or e["target_type"] != "macro_factor":
                continue
            self.adj.setdefault(e["source_code"], []).append({
                "target": e["target_code"],
                "weight": float(e["weight"]),
                "direction": float(e["direction"]),
                "confidence": float(e["confidence"]),
                "decay": _lag_decay(e["lag_minute"], e["lag_max_minute"]),
            })

    def propagate(self, signals):
        """signals: {factor_code: signal_value}（-1~+1）
        返回 {factor_code: {value, confidence, path}}，含图传导后的有效信号。"""
        # 输入信号本身视为高置信（来自数据源或情景）
        sig = {c: {"value": float(v), "conf": 0.7, "path": [c]}
               for c, v in signals.items()}
        # 多跳传播：每轮把源信号经边累加到目标
        for _ in range(MAX_DEPTH):
            incoming = {}
            for src, item in sig.items():
                if abs(item["value"]) < 1e-6:
                    continue
                for edge in self.adj.get(src, []):
                    tgt = edge["target"]
                    contrib = (item["value"] * edge["weight"] * edge["direction"]
                               * edge["confidence"] * edge["decay"] * HOP_DAMPING)
                    inc = incoming.setdefault(tgt, {"value": 0.0, "src": src})
                    inc["value"] += contrib
            if not incoming:
                break
            for tgt, inc in incoming.items():
                if tgt not in sig:
                    sig[tgt] = {"value": 0.0, "conf": 0.5, "path": [tgt]}
                # 目标因子接收传播量（叠加自身已有传导量）
                sig[tgt]["value"] = max(-1.0, min(1.0, sig[tgt]["value"] + inc["value"]))
                if inc["value"] and sig[tgt]["path"][-1] != inc["src"]:
                    sig[tgt]["path"] = [inc["src"], tgt] if len(sig[tgt]["path"]) == 1 \
                        else [inc["src"], sig[tgt]["path"][-1], tgt]
        return sig


def explain_edges():
    """图边清单（用于 API/调试）"""
    out = []
    for e in macro_repo.get_edges():
        if e["source_type"] == "macro_factor" and e["target_type"] == "macro_factor":
            out.append(f"{e['source_name']} → {e['target_name']} "
                       f"(w={float(e['weight']):+.2f}, d={float(e['direction']):+.0f}, "
                       f"conf={float(e['confidence']):.2f})")
    return out
