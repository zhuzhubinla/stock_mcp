"""SEC EDGAR 新闻源实现（免费、无需 API key，需 User-Agent）

数据来源：https://data.sec.gov/submissions/CIK{cik}.json
ticker → CIK 映射：https://www.sec.gov/files/company_tickers.json
把公司申报文件（8-K/10-K/10-Q 等）作为新闻事件。
"""
from datetime import datetime

import requests

from config import SEC_USER_AGENT
from .base import NewsProvider, NewsItem

_HEADERS = {"User-Agent": SEC_USER_AGENT}
# 与股价相关的申报类型（其余如 FWP/424B 等招股类暂忽略）
_INTERESTING_FORMS = {"8-K", "10-K", "10-Q", "6-K", "20-F", "S-1", "DEF 14A", "SC 13D", "SC 13G", "4", "144"}


class SECProvider(NewsProvider):
    code = "sec"
    name = "SEC EDGAR"
    base_url = "https://data.sec.gov"

    @classmethod
    def is_configured(cls) -> bool:
        return True

    def __init__(self):
        self._cik_map = None

    def _get_cik(self, symbol):
        """ticker -> CIK 字符串（10 位补零）。找不到返回 None。"""
        if self._cik_map is None:
            r = requests.get("https://www.sec.gov/files/company_tickers.json",
                             headers=_HEADERS, timeout=30)
            r.raise_for_status()
            self._cik_map = {row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                             for row in r.json().values()}
        return self._cik_map.get(symbol.upper())

    def get_news(self, symbol, start_time, end_time):
        cik = self._get_cik(symbol)
        if not cik:
            return []

        r = requests.get(f"{self.base_url}/submissions/CIK{cik}.json",
                         headers=_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", []) or []
        dates = recent.get("filingDate", []) or []
        accessions = recent.get("accessionNumber", []) or []
        docs = recent.get("primaryDocument", []) or []
        company = data.get("name") or symbol.upper()

        items = []
        for i in range(len(forms)):
            form = forms[i]
            if form not in _INTERESTING_FORMS:
                continue
            try:
                fdate = datetime.strptime(dates[i], "%Y-%m-%d")
            except (ValueError, IndexError):
                continue
            if not (start_time <= fdate <= end_time):
                continue
            acc = accessions[i].replace("-", "")
            doc = docs[i] if i < len(docs) else ""
            url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/{doc}" if doc else ""
            items.append(NewsItem(
                source_news_id=f"{cik}-{acc}-{form}",
                title=f"{form} 申报 | {company}",
                summary=f"{symbol} 于 {dates[i]} 提交 {form} 申报文件",
                content="",
                url=url,
                image_url="",
                author="SEC EDGAR",
                publisher="SEC",
                language="en",
                published_at=fdate,
            ))
        return items
