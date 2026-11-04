# Banking Documentation Review Assistant

Turns a revolving credit facility agreement into a treasury review checklist of 18 items (amount, margin, fees, notice periods, covenant, reporting deadlines, change of control, cross-default, governing law). Each answer cites its clause, comes with the source text, and waits for a reviewer's confirmation.

## Problem

Treasury teams hold many bank documents: facility agreements, fee letters, account mandates, guarantees. Answering "what is our cross-default threshold?" or "how much notice do we need to prepay?" means reading long agreements again. An AI summary helps only if every answer can be traced to a clause, and a wrong figure is caught before anyone relies on it.

## Data

- `data/sample_facility_agreement.txt`: a **fictional** EUR 1.5bn multicurrency revolving facility agreement written for this project (invented parties and terms, in the style of a standard syndicated loan agreement). Its known contents give an answer key for evaluation.
- Real agreements: public companies file credit agreements as exhibits (usually Exhibit 10) on SEC EDGAR. `review.py --doc <file.pdf>` reads PDFs as well as text.

## Method

1. **Clause-level chunking.** The agreement is split by clause number (e.g. 6.1, 11.2); each definition in clause 1.1 becomes its own chunk. Every answer can therefore cite a clause.
2. **Retrieval.** TF-IDF over the chunks (no model download, runs anywhere). Each checklist item retrieves its 3 most relevant clauses.
3. **Extraction.**
   - With `GROQ_API_KEY` set: an LLM reads only the 3 retrieved clauses and returns JSON with the value, the clause number and an exact quote, or `found: false`.
   - Without a key ("locate-only" mode): the top clause and its text are placed in the checklist and the reviewer writes the value. This is the safe default.
4. **Grounding checks** on every LLM answer:
   - the quote must appear word for word in the cited clause;
   - the cited clause must be one of the retrieved clauses;
   - every number in the value must appear in the quote.
   A failed check marks the row "CHECK FAILED - verify manually".
5. **Checklist output** (`outputs/checklist.csv` and `.md`): item, value, clause, source text, status, the other candidate clauses, and blank `confirmed_by` and `reviewer_correction` columns.

## Results (fictional sample agreement)

| Measure | Result |
|---|---|
| Answer clause ranked first | 17 of 18 items |
| Answer clause within top 3 | 18 of 18 items |
| Grounding checks behaving as expected (correct answer, wrong number, invented quote, uncited clause, honest not-found) | 5 of 5 cases |

The one top-1 miss: "total amount of the facility" ranked the Majority Lenders clause (which also mentions Total Commitments) above the definition. Full table: `outputs/results.md`.

## Limitations

- **In-sample results.** The checklist questions and the sample agreement were written together, so retrieval scores here are optimistic. The real test is a set of agreements nobody tuned the questions on (e.g. 5 EDGAR credit agreements).
- **LLM path not yet tested here** (built without API access). The grounding checks are tested with hand-written good and bad answers in `evaluate.py`.
- The checks prove an answer is *quoted* from the document, not that it is *complete*. A value that drops a condition (e.g. the lower euro notice period in clause 4.1) still passes; the reviewer reads the source text for that.
- TF-IDF matches words, not meaning. Agreements that use different wording ("Facility Amount" vs "Total Commitments") may need extra search words in `checklist.py` or an embedding model.
- PDF text extraction can break clause numbering on scanned or two-column documents.

## Where a human signs off

Every row. Status tells the reviewer where to look harder; `confirmed_by` stays blank until a person fills it.

## Success measures for a real pilot

Minutes per agreement against a manual review, share of rows confirmed without correction, rows marked CHECK FAILED that were in fact wrong, and items reviewers had to find outside the cited clause.

## Interactive demo

`streamlit run app.py` opens a four-tab app:

| Tab | What it shows |
|---|---|
| Run the review | Each of the 18 questions runs step by step: the search over all clauses, the top matches with their relevance scores, the extracted answer, and each grounding check passing or failing |
| Try to break it | Write an answer the way an LLM might (wrong number, invented quote, uncited clause) and see the checks accept or reject it; works without an API key |
| Document viewer | The full agreement by section, with the clause behind any answer highlighted |
| Checklist sign-off | The reviewer fills or corrects each value, ticks confirmed, and saves under their name to `outputs/checklist_signed_off.csv` |

Uploads (.txt, .pdf, .docx) are supported from the sidebar. While a review is running, wait for it to finish before clicking elsewhere: Streamlit restarts the run on any click.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py                               # interactive demo
python review.py                                   # locate-only mode
export GROQ_API_KEY=...; python review.py          # LLM extraction + grounding checks
python review.py --doc path/to/credit_agreement.pdf
python evaluate.py                                 # outputs/results.md
```
