# summarize (step 13)
Purpose: a short card per candidate that says why it ranked where it did, so the forecaster can confirm or reject it without reading the score table.

Input: one row of the score table (step 5) with its per-feature breakdown, the candidate table row (names, indication, flags), the `Target`, the feature weights, and the analog's approved evidence (io, wide).

Output ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts), summary card): `summarize.card(...)` → dict `analog_id`, `drug_name`, `rank`, `similarity`, `headline`, `similarities[]`, `differences[]`, `score_breakdown` (feature → {score, weight}), `flags[]`, `sources[]` ({field, quote, url}), `generated_by` (`template` / `gemini`). `summarize.render(card)` → plain text for the CLI. `summarize.Summarizer(mode, llm, cache_dir)` builds cards with one setting for the run. CLI: `--summaries template|gemini|auto` (default from `scoring.yaml`).

Depends on: steps 1–6 (score table, candidate table, loop); `llm.get_llm` for the Gemini path.

Decisions made:
- **The template card is the default and always works offline.** `summaries: template` in `scoring.yaml`; `auto` uses Gemini only when `GEMINI_API_KEY` is set; `gemini` without a key is an error. The template is built from the facts only, so it can't say anything the data doesn't.
- **What the template says:**
  - **Headline:** rank, similarity, and the strongest reason: same ATC 4 class (named), else same ATC 3 class, else the indication words both share, else "text only".
  - **Similarities:** the shared ATC level (named), the indication words both labels use (for Torevia's analogs: "schizophrenia"), and any approved line of therapy, dosing or competitor value that matches.
  - **Differences:** a different ATC 4 class (named), indication words only the analog has (Nuplazid: "hallucinations, delusions, parkinson's disease psychosis"), approved values that don't match, and evidence that isn't used while `use_evidence` is off.
  - **Words** come from the "indicated for" sentences (`embed.indication_statement`), lower-cased, minus stop words, brand names and label boilerplate ("indicated", "treatment", "patients", "adults"…); at most 6 per list.
- **Score breakdown** lists only the features that were scored for this analog (score not blank, weight > 0), with their weights, so the card adds up to the similarity.
- **Flags** are the candidate table's warnings in words (label expansion, multi-route, low volume, peak not confirmed, weak Bass fit).
- **Sources** are the approved evidence quotes and links for the analog; none for analogs without approved values.
- **The Gemini path gets the facts as JSON only** and writes only `headline`, `similarities` and `differences`; breakdown, flags and sources always come from the data. After generation, every number in the text must appear in the facts, and every capitalized word that looks like a drug or company name must be a name in the facts; otherwise the template card is used and `generated_by` says `template (model output failed the fact check)`. Not run live yet (no key); tested with `FakeLLM`.
- **Cache:** Gemini cards are saved in `data/cache/cards/<scenario>/<analog_id>-<hash of the facts>.json` (gitignored), so a rejection loop doesn't call the API again for a card it already wrote. Template cards aren't cached (they're instant).
- **The CLI shows a card for each candidate it asks about** (the top 5, then each replacement), and with `--auto-confirm` a card for each confirmed analog.

Open questions:
- Who signs off on the template's wording and length? Decides: team, at the step 14 demo.

Done when: the CLI shows a card for each of the top 5 and for a replacement after a rejection ✅ (`tests/test_cli.py`); without an API key, template cards appear and everything still runs ✅ (`tests/test_summarize.py`, all offline).
