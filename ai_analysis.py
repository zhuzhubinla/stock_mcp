from openai import OpenAI

from config import *


client=OpenAI(

api_key=OPENAI_KEY,

base_url=OPENAI_BASE

)



def analyze(stock):


    prompt=f"""

你是一名专业美股分析师。


分析下面股票：


{stock}



请输出：

1. 今日走势原因

2. 新闻影响

3. 基本面变化

4. AI产业链影响

5. 风险

6. 是否值得关注



不要给投资建议，只做分析。

"""



    response=client.chat.completions.create(

        model=MODEL,

        messages=[

        {

        "role":"system",

        "content":
        "你是金融分析AI"

        },

        {

        "role":"user",

        "content":prompt

        }

        ]

    )


    return response.choices[0].message.content