import requests, os, time

HEADERS = {"User-Agent": "Arya aryaramani94@gmail.com"}
WATCHLIST = {"AAPL": "0000320193", "MSFT": "0000789019", "TSLA": "0001318605"}
FORMS = {"10-K", "10-Q", "8-K"}
PER_COMPANY = 3

os.makedirs("data", exist_ok=True)

for ticker, cik in WATCHLIST.items():
    meta = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=HEADERS).json()
    r = meta["filings"]["recent"]
    saved = 0
    for form, date, acc, doc in zip(r["form"], r["filingDate"], r["accessionNumber"], r["primaryDocument"]):
        if form not in FORMS:
            continue
        path = f"data/{ticker}_{form}_{date}.html"
        if os.path.exists(path):
            print("skip", path)
        else:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
            with open(path, "wb") as f:
                f.write(requests.get(url, headers=HEADERS).content)
            print("saved", path)
            time.sleep(0.5)
        saved += 1
        if saved == PER_COMPANY:
            break