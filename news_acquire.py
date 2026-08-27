import finnhub
from datetime import datetime,timedelta

from config import FINNHUB_API_KEY


client=finnhub.Client(
    api_key=FINNHUB_API_KEY
)



def get_news(symbol):


    end=datetime.now()


    start=end-timedelta(days=2)



    result=client.company_news(

        symbol,

        start.strftime("%Y-%m-%d"),

        end.strftime("%Y-%m-%d")

    )


    news=[]


    for n in result[:5]:

        news.append({

            "title":
                n.get("headline"),

            "summary":
                n.get("summary"),

            "url":
                n.get("url")

        })


    return news