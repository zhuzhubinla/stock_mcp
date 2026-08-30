"""Investment Intelligence Pipeline（设计文档第 23 节 Agent 工作流 / 第 30 节最终目标）

User → Entity Resolution → Graph(Company/Industry/Chain) → Retrieve(Data Engine)
  → Precondition(Context Vector + Market Precondition) → Expectation Gap
  → Signal Extraction → Conflict / Confidence → Dynamic Scoring → Scenario
  → Risk/Reward → Snapshot → Investment Intelligence

Phase 8：每一步的结果都持久化，供 Online Learning / Continuous Calibration 回填学习。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.adapters import stock_service
from data.repositories import mysql_db as db
from analytics import trend, scoring as legacy_scoring

from context.regime_detector import detect_regime, get_latest_regime
from context.precondition_engine import build_context
from context.expectation_engine import expectation_gap
from signals import conflict as conflict_engine
from scoring.score_engine import compute_score, save_snapshot, direction_of
from scoring.weight_engine import get_weight_config

STEP = lambda name, data: {"step": name, "data": data}  # noqa: E731


def intelligence(symbol, persist=True, force_refresh=False, with_valuation=True):
    """Phase 8 全链路 Intelligence（单只股票）"""
    symbol = symbol.upper()
    chain = []

    # 0. Market Regime（市场层 precondition，一次检测全市场共享）
    regime = detect_regime(persist=persist) if force_refresh else get_latest_regime()
    chain.append(STEP("market_regime", {
        "regime": regime.get("regime"), "regime_score": regime.get("regime_score"),
        "trend": regime.get("trend_score"), "volatility": regime.get("volatility_score"),
        "macro": regime.get("macro_score"),
    }))

    # 1. Data Engine（行情/新闻/基本面/技术）
    quote = stock_service.get_quote(symbol, force_refresh=force_refresh)
    hist = stock_service.get_history(symbol, days=120, force_refresh=force_refresh)
    news = stock_service.get_news(symbol, limit=5, force_refresh=force_refresh)
    fundamentals = stock_service.get_fundamentals(symbol, force_refresh=force_refresh)
    ind = trend.compute_indicators(hist.get("bars", [])) if hist.get("bars") else {}
    chain.append(STEP("data_engine", {
        "quote": quote, "news_count": news.get("count", 0),
        "fundamental_count": len(fundamentals.get("metrics", [])),
        "technical": {k: ind.get(k) for k in ("rsi14", "macd", "ma20", "ma60", "volatility_20d")},
    }))

    # 2. Precondition / Context Vector（含 Market Precondition 注入）
    ctx = build_context(symbol, persist=persist,
                        market_regime=regime.get("regime_score"))
    chain.append(STEP("precondition", ctx))

    # 3. Expectation Gap（Actual vs Expected vs Priced-in）
    exp = expectation_gap(symbol)
    chain.append(STEP("expectation", exp))

    # 4. Signal Extraction（复用 legacy 信号引擎输出 6 类信号分）
    signals = legacy_scoring.compute_total(quote, ind, news.get("news", []),
                                           fundamentals.get("metrics", []))
    # 映射到 0~100 成分分
    comp_raw = {c["name"].split()[0].lower(): c["score"] for c in signals["components"]}
    # Prediction 成分：真实预测信号（无则中性 50）
    from domain.prediction.mapper import stock_prediction_score
    pred = stock_prediction_score(symbol)
    component_scores = {
        "fundamental": _map_signal(comp_raw.get("fundamental"), 1.0),
        "market": _map_signal(comp_raw.get("market") if comp_raw.get("market") is not None
                              else comp_raw.get("price"), 0.6),
        "news": _map_signal(comp_raw.get("news"), 0.8),
        "prediction": pred["score"],  # Phase 8：Prediction Intelligence 真实分
    }
    # Expectation 调整（设计文档第 6 节：surprise 正 → fundamental 加成，priced-in 高 → 减成）
    if exp.get("signal_adjustment"):
        component_scores["fundamental"] += exp["signal_adjustment"] * 15
    chain.append(STEP("signal_extraction", {"legacy_total": signals["total_score"],
                                            "component_scores_0_100": component_scores,
                                            "prediction_detail": {"score": pred["score"],
                                                                   "signals": pred["signals"][:3]}}))

    # 5. Conflict + Confidence
    conflicts = conflict_engine.detect_conflicts(component_scores)
    if persist:
        conflict_engine.save_conflicts(symbol, conflicts)
    chain.append(STEP("conflict", {"conflicts": conflicts}))

    # 6. Dynamic Scoring（0-100 + 置信度 + 方向）
    score_result = compute_score(
        component_scores, context_vector=ctx.get("context_vector"),
        sources=["finnhub", "nasdaq", "sec", "llm"],
        signals=[component_scores.get("fundamental"), component_scores.get("market"),
                 component_scores.get("news")],
        ages_hours=_ages_hours(quote, news, fundamentals),
        n_samples=max(len(news.get("news", [])), len(fundamentals.get("metrics", []))),
        model_version="intelligence-v1")
    chain.append(STEP("dynamic_scoring", score_result))

    # 7. Scenario + Valuation（复用现有 financial_model）
    scenario = None
    valuation = None
    if with_valuation:
        try:
            from financial_model.scenario import run_scenarios
            from financial_model.valuation import estimate
            scenario = run_scenarios(symbol, persist=persist)
            valuation = estimate(symbol, persist=persist)
        except Exception as e:
            print(f"[intelligence] scenario/valuation 失败: {e}")
    chain.append(STEP("scenario_valuation", {
        "scenario": scenario and {k: scenario[k] for k in ("base_eps", "scenarios") if k in scenario},
        "valuation": valuation and valuation.get("price_band"),
    }))

    # 8. Risk/Reward（简化：Bear 目标 vs 现价）
    risk_reward = _risk_reward(quote, valuation, score_result)
    chain.append(STEP("risk_reward", risk_reward))

    # 9. Snapshot 持久化（Phase 8 回测/校准数据基础）
    snapshot_id = None
    if persist:
        snapshot_id = save_snapshot(symbol, score_result)
    chain.append(STEP("snapshot", {"snapshot_id": snapshot_id}))

    return {
        "symbol": symbol,
        "intelligence_version": "phase8-v1",
        "market_regime": regime.get("regime"),
        "overall_score": score_result["overall_score"],
        "confidence": score_result["confidence"],
        "direction": score_result["direction"],
        "snapshot_id": snapshot_id,
        "steps": chain,
        "step_count": len(chain),
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _map_signal(v, scale=1.0):
    """legacy -100~100 信号 → 0~100 成分分"""
    if v is None:
        return 50.0
    return max(0.0, min(100.0, 50.0 + float(v) * scale))


def _ages_hours(quote, news, fundamentals):
    """数据新鲜度（小时）"""
    ages = []
    t = quote.get("time")
    if t:
        try:
            dt = datetime.strptime(str(t)[:19], "%Y-%m-%d %H:%M:%S")
            ages.append((datetime.now() - dt).total_seconds() / 3600)
        except Exception:
            pass
    for n in news.get("news", [])[:3]:
        pa = n.get("published_at")
        if pa:
            try:
                dt = datetime.strptime(str(pa)[:19], "%Y-%m-%d %H:%M:%S")
                ages.append((datetime.now() - dt).total_seconds() / 3600)
            except Exception:
                pass
    return ages if ages else None


def _risk_reward(quote, valuation, score_result):
    """Risk/Reward：Expected Upside vs Downside（设计文档第 16 节简化版）"""
    price = quote.get("price")
    if not price or not valuation:
        return {"note": "数据不足，跳过 Risk/Reward"}
    band = valuation.get("price_band", {})
    bull = band.get("bull", {}).get("target_high")
    bear = band.get("bear", {}).get("target_low")
    if not bull or not bear:
        return {"note": "估值区间缺失"}
    upside = bull / price - 1
    downside = bear / price - 1
    ratio = abs(upside / downside) if downside else None
    return {
        "current_price": price,
        "bull_target": bull,
        "bear_target": bear,
        "expected_upside": round(upside, 4),
        "downside": round(downside, 4),
        "risk_reward_ratio": round(ratio, 2) if ratio else None,
        "direction": score_result["direction"],
    }


if __name__ == "__main__":
    import json
    r = intelligence("NVDA", persist=False)
    print(json.dumps({k: r[k] for k in ("symbol", "market_regime", "overall_score",
                                        "confidence", "direction")}, ensure_ascii=False, indent=1))
    for s in r["steps"]:
        print(f"  [{s['step']}]", json.dumps(s["data"], ensure_ascii=False, default=str)[:120])
