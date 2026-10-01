import json, re
from typing import List, Literal
from pydantic import BaseModel
from ollama import Client

MODEL = "qwen2.5:3b"
client = Client(timeout=300)

class Entity(BaseModel):
    name: str
    type: Literal["Company", "Person", "Event"]

class Relation(BaseModel):
    source: str
    relation: Literal["CEO_OF", "ACQUIRED", "SUBSIDIARY_OF"]
    target: str

class Extraction(BaseModel):
    entities: List[Entity]
    relations: List[Relation]

PROMPT = """Read this excerpt from a company filing.
1. List every company and person named in the text (type Company or Person). Products and services (like Windows, Edge, iPhone) are NOT companies. Skip generic words like "the Company" or "we".
2. List a relation ONLY if the text directly states it: X is CEO of Y (CEO_OF), X acquired Y (ACQUIRED), or X is a subsidiary of Y (SUBSIDIARY_OF). Otherwise leave relations empty.
Never invent names that are not in the text.

TEXT:
{text}"""

GENERIC = {"company", "the company", "registrant", "the registrant", "we", "us", "our"}
COMMON = GENERIC
FILERS = {
    "AAPL": {"name": "Apple Inc.", "aliases": {"apple", "apple inc."} | COMMON},
    "MSFT": {"name": "Microsoft Corporation", "aliases": {"microsoft", "microsoft corporation"} | COMMON},
    "TSLA": {"name": "Tesla, Inc.", "aliases": {"tesla", "tesla, inc."} | COMMON},
}
HONOR = re.compile(r"^(mr|ms|mrs|dr)\.?\s", re.I)

def norm(s):
    return s.strip().lower()

def canon(name, ticker):
    return FILERS[ticker]["name"] if norm(name) in FILERS[ticker]["aliases"] else name.strip()

def valid_entity(e, text):
    n = e.name.strip()
    if len(n) < 3 or not n[0].isupper() or norm(n) in GENERIC:
        return False
    if "securities and exchange commission" in norm(n):
        return False
    if norm(n) not in text.lower():
        return False
    if e.type == "Person" and (HONOR.match(n) or len(n.split()) < 2 or any(ch.isdigit() for ch in n)):
        return False
    return True

def clean(ex, text, ticker):
    entmap = {}
    for e in ex.entities:
        if valid_entity(e, text):
            entmap[norm(e.name)] = Entity(name=canon(e.name, ticker), type=e.type)

    def resolve(n):
        k = norm(n)
        if k in entmap:
            return entmap[k]
        if k in FILERS[ticker]["aliases"]:
            return Entity(name=FILERS[ticker]["name"], type="Company")
        return None

    rels, dropped = [], []
    for r in ex.relations:
        s, t = resolve(r.source), resolve(r.target)
        if not s or not t:
            dropped.append((r, "unknown or invalid entity"))
        elif s.name == t.name:
            dropped.append((r, "same entity on both sides"))
        elif r.relation == "CEO_OF" and not (s.type == "Person" and t.type == "Company"):
            dropped.append((r, "CEO_OF needs Person and Company"))
        elif r.relation in ("ACQUIRED", "SUBSIDIARY_OF") and not (s.type == "Company" and t.type == "Company"):
            dropped.append((r, "needs two Companies"))
        else:
            rels.append(Relation(source=s.name, relation=r.relation, target=t.name))
    ents = list({e.name: e for e in entmap.values()}.values())
    return ents, rels, dropped

KEYWORDS = ["acquired", "acquisition", "subsidiary", "chief executive officer", "ceo", "appointed", "merger"]
allc = json.load(open("chunks.json"))
hits = [c for c in allc if any(k in c["text"].lower() for k in KEYWORDS)
        and "us-gaap" not in c["text"] and "xbrli" not in c["text"]]
chunks = hits[::max(1, len(hits) // 40)][:40]
print("matching chunks:", len(hits), "using", len(chunks))

good, bad = [], []
raw_e = raw_r = kept_e = kept_r = 0

for i, c in enumerate(chunks):
    result = None
    for attempt in range(2):
        try:
            resp = client.chat(
                model=MODEL,
                messages=[{"role": "user", "content": PROMPT.format(text=c["text"])}],
                format=Extraction.model_json_schema(),
                options={"temperature": 0, "num_gpu": 0},
            )
            result = Extraction.model_validate_json(resp.message.content)
            break
        except Exception as e:
            print("retry", c["id"], str(e)[:100])
    if not result:
        bad.append(c["id"])
        continue
    ents, rels, dropped = clean(result, c["text"], c["ticker"])
    raw_e += len(result.entities); raw_r += len(result.relations)
    kept_e += len(ents); kept_r += len(rels)
    good.append({"chunk_id": c["id"], "ticker": c["ticker"], "text": c["text"],
                 "entities": [e.model_dump() for e in ents],
                 "relations": [r.model_dump() for r in rels]})
    print(i + 1, "/", len(chunks), c["id"], "| kept", len(ents), "entities,", len(rels), "relations")
    for e in ents:
        print("    ", e.type, ":", e.name)
    for r in rels:
        print("    KEPT:", r.source, r.relation, r.target)
    for r, why in dropped:
        print("    dropped:", r.source, r.relation, r.target, "-", why)
    json.dump(good, open("extracted.json", "w"), indent=1)
    json.dump(bad, open("quarantine.json", "w"), indent=1)

print("done:", len(good), "chunks ok,", len(bad), "failed")
print("entities kept", kept_e, "of", raw_e, "| relations kept", kept_r, "of", raw_r)