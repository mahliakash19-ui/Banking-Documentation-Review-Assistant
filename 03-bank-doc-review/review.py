"""Turn a facility agreement into a review checklist with clause citations.

Steps:
  1. Split the document into clause-level chunks, keeping each clause number.
  2. For each checklist item, retrieve the 3 most relevant clauses (TF-IDF).
  3. Extract the answer:
       - with GROQ_API_KEY: an LLM returns value + clause + exact quote as JSON;
       - without it: the best-matching clause is shown and the value is left
         for the reviewer ("locate-only" mode).
  4. Check each LLM answer: the quote must appear word for word in the cited
     clause, the cited clause must be one that was retrieved, and every number
     in the value must appear in the quote.
  5. Write a checklist where every row waits for a reviewer's confirmation.

Usage: python review.py [--doc data/sample_facility_agreement.txt] [--top-k 3]
"""
import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from checklist import CHECKLIST

LLM_BASE_URL = "https://api.groq.com/openai/v1"
LLM_MODEL = "openai/gpt-oss-20b"
CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.*)")


def load_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    return Path(path).read_text(encoding="utf-8")


def chunk_clauses(text: str) -> pd.DataFrame:
    """One chunk per numbered clause; definition lines become their own chunks under the same number."""
    chunks, current_id, heading = [], None, ""
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        m = CLAUSE_RE.match(line)
        if m and "." not in m.group(1):          # top-level heading, e.g. "6 FEES"
            heading, current_id = m.group(2), m.group(1)
            continue
        if m:                                    # numbered clause, e.g. "6.1 The Borrower shall..."
            current_id = m.group(1)
            chunks.append({"clause": current_id, "heading": heading, "text": m.group(2)})
        elif current_id and line.startswith('"'):  # definition inside 1.1
            chunks.append({"clause": current_id, "heading": heading, "text": line})
        elif chunks and current_id:
            chunks[-1]["text"] += " " + line
    return pd.DataFrame(chunks)


def retrieve(chunks: pd.DataFrame, top_k: int):
    docs = (chunks.heading + " " + chunks.text).str.lower()
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    X = vec.fit_transform(docs)
    results = {}
    for item in CHECKLIST:
        q = vec.transform([(item["question"] + " " + item["search"]).lower()])
        sims = cosine_similarity(q, X).ravel()
        idx = sims.argsort()[::-1][:top_k]
        results[item["id"]] = chunks.iloc[idx].assign(score=sims[idx].round(3))
    return results


PROMPT = """Answer the question using ONLY the clauses below. Reply with JSON only:
{{"found": true|false, "value": "<short answer with the exact figures>", "clause": "<clause number>", "quote": "<exact words copied from that clause>"}}
If the clauses do not answer the question, reply {{"found": false, "value": "", "clause": "", "quote": ""}}.

Question: {question}

Clauses:
{clauses}"""


def llm_extract(question: str, retrieved: pd.DataFrame) -> dict:
    clauses = "\n".join(f"[{r.clause}] {r.text}" for r in retrieved.itertuples())
    body = json.dumps({
        "model": LLM_MODEL, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": PROMPT.format(question=question, clauses=clauses)}],
    }).encode()
    req = urllib.request.Request(f"{LLM_BASE_URL}/chat/completions", data=body, headers={
        "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(json.loads(resp.read())["choices"][0]["message"]["content"])


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check_answer(ans: dict, retrieved: pd.DataFrame) -> list:
    """Return a list of problems; empty means the answer is grounded in the document."""
    if not ans.get("found"):
        return []
    problems = []
    cited = retrieved[retrieved.clause == str(ans.get("clause", ""))]
    if cited.empty:
        problems.append(f"cited clause {ans.get('clause')} was not among the retrieved clauses")
    elif norm(ans.get("quote", "")) not in norm(" ".join(cited.text)):
        problems.append("quote not found word for word in the cited clause")
    for n in re.findall(r"\d[\d,./]*", ans.get("value", "")):
        if n.rstrip(".,") not in ans.get("quote", ""):
            problems.append(f"number {n} in the value is not in the quote")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="data/sample_facility_agreement.txt")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--out", default="outputs/checklist")
    args = ap.parse_args()

    text = load_text(args.doc)
    chunks = chunk_clauses(text)
    hits = retrieve(chunks, args.top_k)
    use_llm = bool(os.environ.get("GROQ_API_KEY"))
    mode = f"LLM extraction ({LLM_MODEL} via Groq)" if use_llm else "locate-only (no GROQ_API_KEY set)"

    rows = []
    for item in CHECKLIST:
        r = hits[item["id"]]
        if use_llm:
            ans = llm_extract(item["question"], r)
            problems = check_answer(ans, r)
            status = ("not found in document" if not ans.get("found")
                      else "checks passed - confirm" if not problems else "CHECK FAILED - verify manually")
            value, clause, quote = ans.get("value", ""), ans.get("clause", ""), ans.get("quote", "")
        else:
            top = r.iloc[0]
            problems, status = [], "located - reviewer to fill value"
            value, clause, quote = "", top.clause, top.text
        rows.append({"item": item["id"], "question": item["question"], "value": value,
                     "clause": clause, "source_text": quote, "status": status,
                     "problems": "; ".join(problems),
                     "other_candidate_clauses": ", ".join(r.clause.iloc[1:]),
                     "confirmed_by": "", "reviewer_correction": ""})

    df = pd.DataFrame(rows)
    df.to_csv(args.out + ".csv", index=False)
    md = [f"# Facility agreement review checklist", "",
          f"Document: `{args.doc}`. Mode: {mode}. Clauses indexed: {len(chunks)}.", "",
          "Every row needs a reviewer's confirmation before use.", "",
          "| Item | Value | Clause | Source text | Status |", "|---|---|---|---|---|"]
    for r in rows:
        src = r["source_text"].replace("|", "/")
        md.append(f"| {r['item']} | {r['value'] or '—'} | {r['clause']} | {src} | {r['status']} |")
    Path(args.out + ".md").write_text("\n".join(md) + "\n")
    print(f"Mode: {mode}. {len(chunks)} clause chunks. Checklist -> {args.out}.csv / .md")


if __name__ == "__main__":
    main()
