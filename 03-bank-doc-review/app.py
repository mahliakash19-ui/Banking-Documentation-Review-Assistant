"""Banking documentation review: interactive demo.

Shows each stage of the pipeline as it runs: clause chunking, retrieval with
scores, extraction, and the grounding checks that reject unsupported answers.
A reviewer then confirms or corrects every row of the checklist.

Usage: streamlit run app.py
"""
import html
import io
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from checklist import CHECKLIST
from review import check_answer, chunk_clauses, llm_extract, retrieve

SAMPLE = Path("data/sample_facility_agreement.txt")
SIGNED = Path("outputs/checklist_signed_off.csv")

st.set_page_config(page_title="Bank documentation review", layout="wide")
st.markdown("""
<style>
mark {background:#fff3b0; padding:2px 3px; border-radius:3px}
.clause {font-family: ui-monospace, monospace; font-size:0.85rem; padding:4px 8px; border-left:3px solid #ddd; margin:2px 0}
.clause.hit {border-left:3px solid #f0b400; background:#fffbe6}
</style>""", unsafe_allow_html=True)


def read_upload(f) -> str:
    name, data = f.name.lower(), f.getvalue()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Document")
    src = st.radio("Agreement", ["Sample facility agreement (fictional)", "Upload my own"])
    if src.startswith("Sample"):
        text, doc_name = SAMPLE.read_text(), SAMPLE.name
    else:
        up = st.file_uploader("Facility agreement", type=["txt", "pdf", "docx"],
                              help="A loan or credit facility agreement with numbered clauses (1.1, 6.2, ...). "
                                   "PDFs need selectable text. Public examples: credit agreements filed as "
                                   "Exhibit 10 on SEC EDGAR.")
        if not up:
            st.info("Upload an agreement to start.")
            st.stop()
        text, doc_name = read_upload(up), up.name

    st.header("Extraction")
    has_key = bool(os.environ.get("GROQ_API_KEY"))
    use_llm = st.checkbox("Use LLM to extract answers (Groq)", value=has_key, disabled=not has_key,
                          help="Needs GROQ_API_KEY set before starting the app. Without it the app runs in "
                               "locate-only mode: it finds the clause and the reviewer reads the value.")
    top_k = st.slider("Clauses retrieved per question", 1, 5, 3)
    speed = st.select_slider("Animation speed", ["Fast", "Normal", "Slow"], value="Normal")
    delay = {"Fast": 0.05, "Normal": 0.35, "Slow": 0.9}[speed]
    st.header("Reviewer")
    reviewer = st.text_input("Your name (needed to sign off)")

chunks = chunk_clauses(text)
if chunks.empty:
    st.error("No numbered clauses found. The tool expects clauses numbered like 1.1, 6.2, 11.4.")
    st.stop()

doc_key = (doc_name, len(text), use_llm, top_k)
if st.session_state.get("doc_key") != doc_key:
    st.session_state.update(doc_key=doc_key, results=None)

st.title("Banking documentation review")
st.caption(f"{doc_name} · {len(chunks)} clause chunks · "
           f"{'LLM extraction (' + 'openai/gpt-oss-20b via Groq)' if use_llm else 'locate-only mode (no LLM)'} · "
           "every answer cites its clause and waits for a reviewer")

tab_run, tab_break, tab_doc, tab_sign = st.tabs(
    ["▶ Run the review", "🧪 Try to break it", "📄 Document viewer", "✅ Checklist sign-off"])


def clause_html(row, highlight_quote=None, hit=False):
    body = html.escape(row.text)
    if highlight_quote:
        q = html.escape(highlight_quote.strip())
        if q and q in body:
            body = body.replace(q, f"<mark>{q}</mark>", 1)
    return f"<div class='clause{' hit' if hit else ''}'><b>[{row.clause}]</b> {body}</div>"


# ---------------------------------------------------------------- 1 run
with tab_run:
    st.markdown("Each question goes through four steps: **search** all clauses, keep the **top matches**, "
                "**extract** the answer, and run the **grounding checks**. Watch them run below.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Checklist questions", len(CHECKLIST))
    c2.metric("Clause chunks indexed", len(chunks))
    c3.metric("Mode", "LLM + checks" if use_llm else "Locate-only")

    with st.expander("Step 0: how the agreement was split into clauses"):
        st.dataframe(chunks.assign(text=chunks.text.str.slice(0, 120) + "…"), hide_index=True,
                     use_container_width=True)

    if st.button("▶ Run review", type="primary"):
        hits = retrieve(chunks, top_k)
        progress = st.progress(0.0, text="Starting")
        results = []
        for i, item in enumerate(CHECKLIST, 1):
            r = hits[item["id"]]
            progress.progress(i / len(CHECKLIST), text=f"Question {i} of {len(CHECKLIST)}: {item['id']}")
            with st.status(f"{i}. {item['question']}", expanded=True) as box:
                st.write(f"🔎 Searching {len(chunks)} clauses for: *{item['search']}*")
                time.sleep(delay)
                st.write(f"📑 Top {len(r)} clauses by relevance score:")
                top = r.score.max() or 1
                for row in r.itertuples():
                    cols = st.columns([1, 4])
                    cols[0].progress(float(row.score / top), text=f"[{row.clause}] {row.score:.2f}")
                    cols[1].markdown(clause_html(row, hit=row.Index == r.index[0]), unsafe_allow_html=True)
                    time.sleep(delay / 2)

                if use_llm:
                    st.write("🤖 Asking the LLM to answer from these clauses only, with an exact quote…")
                    try:
                        ans = llm_extract(item["question"], r)
                    except Exception as e:  # network or rate limit: fall back for this item
                        ans = {"found": False, "value": "", "clause": "", "quote": ""}
                        st.warning(f"LLM call failed ({e.__class__.__name__}); falling back to locate-only.")
                    problems = check_answer(ans, r)
                    time.sleep(delay)
                    if ans.get("found"):
                        st.write(f"Answer: **{ans.get('value')}** · cited clause **{ans.get('clause')}**")
                        st.markdown(f"Quote: “{html.escape(ans.get('quote', ''))}”")
                    else:
                        st.write("Answer: not found in the retrieved clauses.")
                    st.write("🛡️ Grounding checks:")
                    cited = r[r.clause == str(ans.get("clause", ""))]
                    checks = [
                        ("Cited clause was retrieved", not any("not among" in p for p in problems)),
                        ("Quote appears word for word in that clause", not any("quote not found" in p for p in problems)),
                        ("Every number in the answer is in the quote", not any("number" in p for p in problems)),
                    ] if ans.get("found") else []
                    for label, ok in checks:
                        st.write(("✅ " if ok else "❌ ") + label)
                        time.sleep(delay / 2)
                    status = ("not found in document" if not ans.get("found")
                              else "checks passed - confirm" if not problems else "CHECK FAILED - verify manually")
                    value, clause, quote = ans.get("value", ""), ans.get("clause", ""), ans.get("quote", "")
                else:
                    top_row = r.iloc[0]
                    st.write(f"📌 Locate-only: clause **{top_row.clause}** placed in the checklist; "
                             "the reviewer reads it and enters the value.")
                    problems, status = [], "located - reviewer to fill value"
                    value, clause, quote = "", top_row.clause, top_row.text
                time.sleep(delay)
                state = "error" if status.startswith("CHECK FAILED") else "complete"
                box.update(label=f"{i}. {item['question']} → {status}", state=state, expanded=False)
            results.append({"item": item["id"], "question": item["question"], "value": value,
                            "clause": clause, "source_text": quote, "status": status,
                            "problems": "; ".join(problems), "confirmed": False, "reviewer_correction": ""})
        progress.progress(1.0, text="Done")
        st.session_state["results"] = pd.DataFrame(results)

    res = st.session_state.get("results")
    if res is not None:
        n_fail = int(res.status.str.startswith("CHECK FAILED").sum())
        st.success(f"Review finished: {len(res)} items. "
                   + (f"{n_fail} answer(s) failed the grounding checks. " if n_fail else "")
                   + "Go to **Checklist sign-off** to confirm each row.")
        st.dataframe(res[["item", "value", "clause", "status"]], hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- 2 break it
with tab_break:
    st.markdown("This is what stops an LLM from inventing figures. Write an answer the way an LLM might, "
                "then see whether the checks accept it. No API key needed.")
    hits_all = retrieve(chunks, top_k)
    item = st.selectbox("Question", CHECKLIST, format_func=lambda x: x["question"], index=3)
    r = hits_all[item["id"]]
    st.markdown("**Clauses retrieved for this question**")
    for row in r.itertuples():
        st.markdown(clause_html(row), unsafe_allow_html=True)

    presets = {"Correct answer (from the top clause)": None,
               "Wrong number": "wrong", "Invented quote": "quote",
               "Cites a clause that was not retrieved": "clause", "Write my own": "own"}
    choice = st.radio("Start from", list(presets), horizontal=True)
    top_row = r.iloc[0]
    import re as _re
    nums = _re.findall(r"\d[\d,.]*\d|\d", top_row.text)
    good_value = nums[0] if nums else top_row.text[:40]
    default = {"value": good_value, "clause": top_row.clause, "quote": top_row.text[:160]}
    if presets[choice] == "wrong" and nums:
        bumped = nums[0].replace(nums[0][-1], str((int(nums[0][-1]) + 1) % 10), 1)
        default["value"] = bumped
    elif presets[choice] == "quote":
        default["quote"] = "The Borrower may at any time terminate this Agreement without notice."
    elif presets[choice] == "clause":
        other = chunks[~chunks.clause.isin(r.clause)].iloc[-1]
        default.update(clause=other.clause, quote=other.text[:120])

    c1, c2 = st.columns([1, 1])
    value = c1.text_input("Answer value", default["value"], key=f"v_{choice}_{item['id']}")
    clause = c2.text_input("Cited clause", default["clause"], key=f"c_{choice}_{item['id']}")
    quote = st.text_area("Quote the answer claims to come from", default["quote"], key=f"q_{choice}_{item['id']}")
    problems = check_answer({"found": True, "value": value, "clause": clause, "quote": quote}, r)
    if problems:
        st.error("❌ Rejected: " + "; ".join(problems))
    else:
        st.success("✅ Accepted: the quote is in the cited clause and every number in the answer is in the quote. "
                   "A reviewer still confirms it.")
    st.caption("What the checks cannot catch: an answer that is quoted correctly but incomplete (for example, "
               "leaving out an exception in the same clause). That is why every row still needs a reviewer.")

# ---------------------------------------------------------------- 3 document
with tab_doc:
    res = st.session_state.get("results")
    focus_clause, focus_quote = None, None
    if res is not None:
        pick = st.selectbox("Highlight the clause behind an answer", res.item.tolist())
        row = res[res.item == pick].iloc[0]
        focus_clause, focus_quote = str(row.clause), (row.source_text if use_llm else None)
        st.markdown(f"**{row.question}** → clause **{focus_clause}** · {row.status}")
    else:
        st.info("Run the review to highlight the clause behind each answer.")
    heading = None
    for row in chunks.itertuples():
        if row.heading != heading:
            heading = row.heading
            st.markdown(f"#### {heading}")
        st.markdown(clause_html(row, focus_quote if row.clause == focus_clause else None,
                                hit=row.clause == focus_clause), unsafe_allow_html=True)

# ---------------------------------------------------------------- 4 sign-off
with tab_sign:
    res = st.session_state.get("results")
    if res is None:
        st.info("Run the review first.")
    else:
        st.markdown("Read each source clause, fill or correct the value, and tick **confirmed**. "
                    "Rows that failed the grounding checks need a correction or a note before confirming.")
        edited = st.data_editor(
            res, hide_index=True, use_container_width=True, key="signoff",
            disabled=["item", "question", "clause", "source_text", "status", "problems"],
            column_config={"confirmed": st.column_config.CheckboxColumn("confirmed"),
                           "source_text": st.column_config.TextColumn("source text", width="large"),
                           "value": st.column_config.TextColumn("value (fill or correct)")})
        done = int(edited.confirmed.sum())
        st.progress(done / len(edited), text=f"{done} of {len(edited)} rows confirmed")
        blank = edited[edited.confirmed & (edited.value.fillna("").str.strip() == "")]
        if len(blank):
            st.warning(f"{len(blank)} confirmed row(s) have no value: " + ", ".join(blank.item))
        if st.button("Save sign-off", type="primary", disabled=not reviewer):
            out = edited.assign(reviewed_by=reviewer, reviewed_at=datetime.now().isoformat(timespec="seconds"),
                                document=doc_name)
            out.to_csv(SIGNED, mode="a", header=not SIGNED.exists(), index=False)
            st.success(f"Saved {len(out)} rows ({done} confirmed) to {SIGNED} under {reviewer}.")
        if not reviewer:
            st.caption("Enter your name in the sidebar to save.")
