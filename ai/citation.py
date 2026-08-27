"""Citation：引用与来源血缘（Detailed Technical Design 第 13、24 节）
关键数字和结论可追溯到来源文档：结论 → 模型 → 指标 → 原始来源。
"""
import sys
sys.path.append("/home/admin/stock_agent")


def lineage(conclusion, model_id=None, indicator_ids=None, source_ids=None):
    """构建血缘链：conclusion → model → indicators → sources"""
    return {
        "conclusion": conclusion,
        "model_id": model_id,
        "indicators": indicator_ids or [],
        "sources": source_ids or [],
        "traceable": bool(model_id or (indicator_ids and source_ids)),
    }


def cite_source(source_id, source_name, reliability_score, doc_title=None, doc_url=None):
    """单条引用记录"""
    return {
        "source_id": source_id,
        "source_name": source_name,
        "reliability_score": float(reliability_score) if reliability_score is not None else None,
        "document": {"title": doc_title, "url": doc_url},
    }


def attach_citations(result, citations):
    """给分析结果附上引用列表"""
    if isinstance(result, dict):
        result["citations"] = citations
    return result
