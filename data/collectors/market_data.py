"""
Created on 2026/08/04

@author: Eric.Zhu
"""
import sys
from datetime import datetime, timezone, timedelta


import finnhub
import yfinance as yf

sys.path.append("/home/admin/stock_agent")

from config import FINNHUB_API_KEY


client = finnhub.Client(api_key=FINNHUB_API_KEY)


def stock_data_get_from_yfinance(symbol):
    stock = yf.Ticker(symbol)
    df = stock.history(period="1mo", interval="1d")
    return df


def stock_data_get_quote(symbol):
    data = client.quote(symbol)
    print("stock_get_quote:{}".format(data))
    return {
        "symbol": symbol,
        "price": data.get("c"),  # Current price
        "change": data.get("d"),  # Change in price
        "percent": data.get("dp"),  # Change in price percent
        "high": data.get("h"),  # High price
        "low": data.get("l"),  # Low price
        "open": data.get("o"),  # Open price
        "prev_close": data.get("pc"),  # Previous close price
        "time": data.get("t"),  # Time of quote
    }


def stock_data_get_company(symbol):
    return client.company_profile(symbol=symbol)


def stock_data_get_financial(symbol):
    return client.company_basic_financials(symbol, "all")


if __name__=="__main__":
    # print(stock_data_get_from_yfinance("NVDA"))
    stock_data = stock_data_get_quote("NVDA")
    utc8 = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(stock_data["time"], tz=utc8)
    print(dt)
    # print(stock_data_get_financial("NVDA"))
