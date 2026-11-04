"""Measure retrieval and grounding checks on the sample agreement.

1. Retrieval: is an answer-key clause the top hit, and is it in the top 3?
2. Grounding checks: does check_answer() reject fabricated answers? Uses
   hand-written good and bad answers, so it runs without an LLM.

Usage: python evaluate.py
"""
import pandas as pd

from checklist import CHECKLIST
from review import check_answer, chunk_clauses, load_text, retrieve

DOC = "data/sample_facility_agreement.txt"


def retrieval_eval(top_k=3):
    hits = retrieve(chunk_clauses(load_text(DOC)), top_k)
    rows = []
    for item in CHECKLIST:
        got = list(hits[item["id"]].clause)
        rows.append({"item": item["id"], "expected": "/".join(item["key_clauses"]),
                     "retrieved": ", ".join(got),
                     "top1": got[0] in item["key_clauses"],
                     "top3": any(c in item["key_clauses"] for c in got)})
    return pd.DataFrame(rows)


def check_eval():
    hits = retrieve(chunk_clauses(load_text(DOC)), 3)
    r = hits["margin"]
    cases = [
        ("correct answer", {"found": True, "value": "0.45% per annum", "clause": "5.2",
                            "quote": "The Margin is 0.45 per cent. per annum"}, True),
        ("wrong number", {"found": True, "value": "0.55% per annum", "clause": "5.2",
                          "quote": "The Margin is 0.45 per cent. per annum"}, False),
        ("invented quote", {"found": True, "value": "0.45%", "clause": "5.2",
                            "quote": "The Margin is fixed at 0.45 per cent."}, False),
        ("clause not retrieved", {"found": True, "value": "0.45%", "clause": "13.1",
                                  "quote": "governed by French law"}, False),
        ("honest not-found", {"found": False, "value": "", "clause": "", "quote": ""}, True),
    ]
    out = []
    for name, ans, should_pass in cases:
        passed = not check_answer(ans, r)
        out.append({"case": name, "expected": "pass" if should_pass else "reject",
                    "result": "pass" if passed else "reject", "correct": passed == should_pass})
    return pd.DataFrame(out)


def main():
    ret = retrieval_eval()
    chk = check_eval()
    lines = ["# Evaluation (fictional sample agreement)", "",
             f"Retrieval over {len(ret)} checklist items: answer clause ranked first for "
             f"{int(ret.top1.sum())}/{len(ret)}, within top 3 for {int(ret.top3.sum())}/{len(ret)}.", "",
             ret.to_markdown(index=False), "",
             f"Grounding checks: {int(chk.correct.sum())}/{len(chk)} cases handled as expected.", "",
             chk.to_markdown(index=False), ""]
    text = "\n".join(lines)
    open("outputs/results.md", "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
