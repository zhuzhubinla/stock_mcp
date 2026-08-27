import requests



HEADERS={

"User-Agent":
"stock-agent admin@example.com"

}



def get_sec(company):


    url=f"https://data.sec.gov/submissions/CIK{company}.json"


    r=requests.get(

        url,

        headers=HEADERS

    )


    return r.json()



def recent_filings(cik):


    data=get_sec(cik)


    recent=data["filings"]["recent"]


    result=[]


    for i in range(5):

        result.append({

        "form":
        recent["form"][i],

        "date":
        recent["filingDate"][i],

        "doc":
        recent["primaryDocument"][i]

        })


    return result