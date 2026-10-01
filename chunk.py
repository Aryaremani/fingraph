import os, re, json
from bs4 import BeautifulSoup

CHUNK_SIZE = 1000   # characters
OVERLAP = 150

def clean(path):
    html = open(path, "rb").read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "table"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()

def chunk(text):
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - OVERLAP
    return out

chunks = []
for name in sorted(os.listdir("data")):
    if not name.endswith(".html"):
        continue
    ticker, form, date = name[:-5].split("_")
    text = clean(f"data/{name}")
    for i, c in enumerate(chunk(text)):
        chunks.append({"id": f"{ticker}_{form}_{date}_{i}", "ticker": ticker,
                       "form": form, "date": date, "text": c})
    print(name, len(text), "chars")

json.dump(chunks, open("chunks.json", "w"), indent=1)
print("total chunks:", len(chunks))