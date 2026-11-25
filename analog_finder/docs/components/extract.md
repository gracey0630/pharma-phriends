# extract and verify (step 11)
Purpose: fill the four label-read fields (line of therapy, dosing frequency, launch date, # competitors at launch) for the analogs in the work queue, each with a value, a quote and a link, written to `data/reference/analog_evidence.csv` as unapproved rows for a person to review (step 12).

Input:
- the work queue (`research/queue.py`, step 10): `todo` items only
- sources, all fetched through the gate (`research/sources.py`): the ORIG label PDF (Drugs@FDA), SEC EDGAR filings, and Drugs@FDA's approval files in `data/raw/drugsfda/` (already downloaded by the pipeline)
- `data/processed/`: `analogs.csv` (indication text, approval date), `analog_features.csv` (launch quarter)
- the language model (`llm.get_llm()`; `FakeLLM` without `GEMINI_API_KEY`)
- `.env`: `GEMINI_API_KEY`, `GEMINI_MODEL`; `SEC_USER_AGENT` (launch dates only)

Output ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)):
- evidence rows appended to `analog_evidence.csv`, `approved=false`, with `quote_check` and `notes` filled
- a run report, `data/raw/research/runs/<timestamp>.csv` (gitignored): one row per queue item tried, with what happened (`written`, `skipped`, or `not written (dry run)`) and why
- `python -m analog_finder.research [--scenario torevia] [--analogs ID ...] [--fields F ...] [--limit N] [--redo] [--dry-run] [--source-url URL]`

Depends on: step 10 (gate and queue); the line-of-therapy categories and the competitor definition (decisions.md 2026-11-19).

## How each field is read

| Field | Source | How | `quote_check` |
|---|---|---|---|
| line_of_therapy | ORIG label, Indications | One model call per label returns both label fields. The category (`first` / `later` / `any` / `not stated`) with the sentence it rests on | verbatim / partial |
| dosing_frequency | ORIG label, Dosage and Administration | Same call. The maintenance frequency in the house style (`once daily`, `twice daily (after 5-day titration)`, `every 4 weeks (loading doses at weeks 0 and 2)`) with its sentence | verbatim / partial |
| launch_date | SEC filings (8-K exhibits, 10-Q, 10-K) | EDGAR full-text search for the brand name in filings from approval to approval + 15 months; the passages around the name go to the model, which says whether one states a launch (`launched`), only plans one (`forecast`), or neither | verbatim / partial |
| n_competitors_at_launch | Drugs@FDA approval history | The model proposes the competitors under the agreed definition; code checks each one in Drugs@FDA and counts only those confirmed | not_checked (each date checked by code; see notes) |

## Decisions made
- **Label fields come from the ORIG label PDF, fetched through the gate** (`pipeline.labels.orig_label_url` for the URL), not `pipeline.labels.download`, so the approved-source rule holds for every fetch. The model gets the label's text up to section 3 (Highlights, Indications, Dosage and Administration), which holds both fields and keeps the prompt short.
- **Quote check (verify.py):** a quote is `verbatim` when all its words appear in order in the source text after normalizing both: lowercase, letters and digits only (so punctuation, line breaks and spacing don't matter), and a word split by a hyphen at a line break joined back (`antipsy-\nchotic`). Otherwise `partial`, with how far it matched in `notes` ("first 12 of 30 words"). Last, the letters are compared with every space removed, because PDF text extraction can split a word (Latuda's label reads "sc hizophrenia"): same characters in the same order still counts as verbatim. This is PR #6's checker (`pipeline.labels._words`) plus the hyphen and split-word rules. Anything else (a changed word, a reordered clause) is partial: the reviewer decides.
- **One retry on a partial quote:** the model is told its quote wasn't found word for word and asked to copy the sentence exactly. If the second answer is still partial, the row is written as `partial`, so a person sees it rather than the agent hiding it.
- **Checks written into `notes`** (new column, so the reviewer sees them next to the value):
  - line of therapy: `score.line_cross_check` against the quote; a disagreement is noted ("keywords in the quote read as later")
  - dosing: `score.doses_per_week` must read the value; if not, noted ("frequency not machine-readable")
  - competitors: each drug proposed and dropped, with why (not found in Drugs@FDA, approved after launch, generic entry before launch)
- **Forecasts are never written as launch dates.** "Expected to be available", "will launch" and similar are `forecast`: nothing is written and the run report keeps the URL and quote, for a person to follow up (the seed 8's `[excerpt, verify]` rows are the case this prevents).
- **Launch date precision:** `YYYY-MM-DD` when the source gives a day, `YYYY-MM` when it gives a month ("launched in February 2011"); never a made-up day. The pipeline uses the quarter only.
- **Launch dates in v1 come from SEC filings only.** EDGAR full-text search is a fixed, approved API; model web search returns redirect links the gate can't check. For companies not registered with the SEC (Lundbeck / Otsuka for Rexulti, Sumitomo for Latuda) a person finds the page on an approved company source and runs `--source-url URL` for that analog; the agent extracts and checks the quote. Model web search is an open question for step 15.
- **Competitors are counted by code, not the model.** The model proposes names (brand, active ingredient, approval year, why it's the same disease and setting); code finds each in Drugs@FDA (`Products.txt` by brand, then the application's ORIG approval in `Submissions.txt`), keeps it only if approved before the analog's launch, and drops it if its generic entered before the launch. **Generic entry:** for a brand in our pool, the first quarter a generic was dispensed in Medicaid (`analogs.csv` `generic / exclusivity date`; blank = none yet); for older brands, the first ANDA approval as a proxy, noted as such. ANDA approval alone is wrong for pool brands: a settlement can delay the launch for years (Latuda: ANDA approved 2019-01, generic dispensed 2023Q1; Rexulti: ANDA approved 2022-08, no generic dispensed). On Torevia's launch (2027-01) the rule gives Rexulti, Vraylar, Caplyta, Lybalvi and Cobenfy, the 5 of decisions.md 2026-11-19. The value is the number kept. The quote lists them in the seed 8's format: `[derived, verify each date] approved for the same indication before launch: Abilify (2002-11-15), ...`. Source: the Drugs@FDA page of the analog's application.
- **Launch point for competitors:** the approved launch date if there is one, else the analog's launch quarter (first SDUD quarter), as in `analog_features`.
- **Re-runs:** only `todo` queue items are read, so an (analog, field) with any row waiting for review is skipped. `--redo` reads it again but still skips writing when the new value and quote match an existing row.
- **No ORIG label, no SEC hit, model says `not stated` / none:** nothing is written for a missing source (the run report says why, and the item stays `todo`). A label that's read but doesn't say (line of therapy `not stated`) is written, since that's a real reading a person can approve.
- **Append only:** rows are only ever appended. Before writing, the existing rows are read back after the write and compared; any difference aborts and restores the file. The header gains `quote_check`, `approved_at` and `notes` (blank for older rows).
- **`extracted_by`** is `agent:<llm name>` (e.g. `agent:gemini:gemini-2.5-flash`); `extracted_at` the run date.
- **Prompts** name the schema (`label_read`, `launch_date`, `competitors`) so `FakeLLM` fixtures drive the tests; tests use saved label text and saved SEC pages, never the network.

- **Without a Gemini key nothing is written:** the model is `FakeLLM`, so the run is a dry run that still fetches the label, checks the gate and Drugs@FDA, and prints what it would do. `--limit` (default 5 analogs a run) keeps a live run small.

Result (2026-11-19, offline, `FakeLLM`): `--analogs latuda_oral` fetches Latuda's ORIG label (`200603s000lbl.pdf`) through the gate; the SEC search is refused until `SEC_USER_AGENT` is set; Drugs@FDA lookups run; nothing written. 29 tests (`tests/test_extract.py`) on a saved label, saved SEC pages and a Drugs@FDA stub. The live run waits for a Gemini key.

## Open questions
- Model web search for launch dates (step 15, when scaling past Torevia's analogs): worth resolving grounding redirect links through the gate?
- Retrying a rejected read (step 15, once rejections start): today a rejected item goes back to `todo`, but the next run isn't told what was rejected or why, and doesn't avoid the rejected link; a repeat of the same value and quote is skipped, so the item can stay `todo` for good. Proposal: label fields (line of therapy, dosing) stay on the ORIG label, with the rejected value and reason given to the model; launch dates and competitor counts skip the rejected `source_url` and try the next hit (or a person's `--source-url`); a retry with nothing new reports "no new source found; needs a person". Decides: team (raised by Grace, 2026-11-24).
- ~~Whether a `partial` quote should block approval~~ Settled in step 12: it doesn't, but approving needs the reviewer's "checked against the source" tick (review.md).

Done when: `python -m analog_finder.research --analogs latuda_oral` adds rows with quotes; label quotes check as verbatim; `git diff` shows no approved row changed; tests run on `FakeLLM` and saved pages.
