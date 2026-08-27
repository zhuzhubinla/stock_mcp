"""Financial Model Engine：把 Driver 转换成公司财务预测
Agent 流程第 9 步（Financial Model）+ 第 10 步（Scenario）。
Revenue = Segment1 Shipment × Share × ASP + Segment2 ... + Other（文档第 21 节）
v2：financial_model（模型头）+ financial_model_line（metric/period/value/formula）
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.adapters import stock_service  # noqa: F401  (行情数据源)
from data.repositories import graph_repo, forecast_repo
from domain.factor import engine as factor_engine


def build_revenue_model(symbol, persist=True):
    """按业务分拆构建营收模型：
    每个 segment 找到对应行业指标（出货量/ASP），
    revenue_segment = indicator_value × share × asp（若有）
    结果写入 financial_model + financial_model_line。
    """
    from domain.business.decomposer import decompose
    segs = decompose(symbol=symbol).get("segments", [])
    if not segs:
        return {"symbol": symbol, "error": "无业务分拆数据"}

    model = []
    total = 0.0
    model_id = None
    company = graph_repo.get_company(symbol=symbol)
    if persist and company:
        model_id = forecast_repo.upsert_financial_model(
            company["id"], name=f"{symbol} Revenue Model", model_type="bottom_up",
            version="v1", base_period="2024-01-01", forecast_start="2026-01-01",
            forecast_end="2027-01-01")

    for s in segs:
        industry_id = s.get("industry_id")
        seg_rev = None
        indicators = []
        if industry_id:
            indicators = factor_engine.indicators(industry_id=industry_id)
            by_name = {}
            for ind in indicators:
                by_name.setdefault(ind["indicator"], []).append(ind)
            shipment = by_name.get("AI 眼镜出货量") or by_name.get("AI 芯片出货量") or \
                by_name.get("shipment") or by_name.get("出货量")
            asp = by_name.get("AI 眼镜 ASP") or by_name.get("ASP") or by_name.get("asp")
            if shipment and asp:
                ship = sorted(shipment, key=lambda x: x["period"] or "")[-1]
                a = sorted(asp, key=lambda x: x["period"] or "")[-1]
                seg_rev = (ship["value"] or 0) * (a["value"] or 0)
        model.append({
            "segment": s["name"], "industry": s.get("industry"),
            "revenue_share": float(s["revenue_share"]) if s.get("revenue_share") is not None else None,
            "estimated_revenue": seg_rev,
            "indicators": [i["indicator"] for i in indicators],
        })
        if seg_rev:
            total += seg_rev
        # 明细行落库
        if persist and model_id:
            forecast_repo.upsert_financial_model_line(
                model_id, "revenue", "2026-01-01", seg_rev,
                business_segment_id=s.get("segment_id"),
                assumption_type="derived" if seg_rev else "missing",
                formula="shipment × asp")
    if persist and model_id:
        forecast_repo.upsert_financial_model_line(model_id, "revenue", "2026-01-01", total,
                                                  assumption_type="derived",
                                                  formula="Σ segment revenue")
    return {"symbol": symbol, "model_id": model_id, "segments": model,
            "total_estimated": round(total, 2), "method": "shipment × ASP（分业务）"}


