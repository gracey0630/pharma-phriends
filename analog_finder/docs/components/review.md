# review (step 12)
Purpose: a person approves, edits or rejects each unapproved evidence row before anything uses it, in the app (page 1) or, as before, in the spreadsheet.

Input: `data/reference/analog_evidence.csv` (every row; [Shared contracts](../../../docs/implementation_plan.md#shared-contracts), evidence row), the work queue (step 10) for the scenario's order, the reviewer's name (typed in the app).

Output:
- `research/review.py`: `load(path)` → every row with its row number and a fingerprint; `to_review(evidence, order)` → the unapproved rows in review order; `decide(path, row, seen, decision, reviewer, ...)` → writes one decision to the file, or raises `ReviewError` and changes nothing.
- The same rows in `analog_evidence.csv`, updated: `approved` = `true` or `rejected`, `approved_by`, `approved_at`, and `notes` (what the reviewer changed or why they rejected). Every other line stays byte for byte.
- `streamlit run analog_finder/app/Home.py`: Home (what's waiting, by status) and page 1, Review.

Depends on: steps 10 (queue) and 11 (the rows, `quote_check` and `notes` columns); `finder.target.LINE_CATEGORIES`, `finder.score.doses_per_week`; streamlit 1.67.0 (added to `analog_finder/requirements.txt`).

Decisions made:
- **Rejected is a third value of `approved`** (`true` / `false` / `rejected`), with the reviewer, time and reason recorded like an approval. Every reader already counts only `true` as approved, so matching is unchanged. Four places that treated "not true" as "waiting" now tell the two apart: the work queue (a rejected item goes back to `todo`, so the agent reads it again; an identical value and quote is never re-written, step 11), `pipeline.build` (a rejected value is never copied into `analogs.csv`), and the `analog_features` and `checks.md` counts. Settles plumbing.md's open question.
- **Editing before approving:** the reviewer can change the value, and the quote, of a row that isn't approved yet; the row is changed in place and `notes` records what it said before ("edited by Joshua: value was 'later'"). `extracted_by` keeps who read it. A changed quote is set to `quote_check = not_checked` until `python -m pipeline.labels --check` reads it again. Line of therapy takes only the four categories; a dosing value the scorer can't read is accepted with a warning in `notes`.
- **A `partial` quote doesn't block approval, but it needs a tick:** "I checked the value against the source". The same tick is required for launch dates and competitor counts, which aren't label quotes (data_model.md, review). The tick is recorded in `notes`. Settles extract.md's open question.
- **Approved and rejected rows are read-only** in the app (CLAUDE.md: never overwrite an approved row). A wrong approval is fixed by a newer approved row for the same analog and field (the latest `approved_at` wins).
- **Safe writes:** each decision re-reads the file and checks the row still says what the reviewer saw (its fingerprint: analog, field, value, quote, link, extraction date, status); if not, nothing is written and the page asks for a reload. The rewrite keeps every other line byte for byte (older short rows too), then reads the file back and restores it if any other row changed. One reviewer per batch still commits the file (Working agreements).
- **Order:** the scenario's queue priority (Torevia: the 5 expected analogs, then the nervous-system analogs, then the rest), then analog, then field in queue order, so a reviewer reads one label once for its two label fields. Rows for analogs outside the queue come last.
- **`approved_at`** = local time to the second (`2026-11-20T14:05:09`), so two approvals on one day still order; the header gains the column if it's missing, as in step 11.
- **The reviewer's name** is typed once in the sidebar and required; the app doesn't read the OS user name (same rule as `loop.py`).

Open questions:
- Correcting an approved value in the app (a new human row with quote and link) isn't built; today that's a spreadsheet row with `extracted_by` = the person. Decides: team, if it comes up in step 15's 164 reviews.

Done when: approving one row saves it as approved ✅ (`tests/test_review.py`, and in the app); spreadsheet review still works on the same file ✅ (a hand-approved row is read the same way; the app leaves other lines byte for byte); Torevia's 20 values are reviewed: waits for step 11's live run (Gemini key).
