# score (step 5)
Purpose: rank candidates by the weighted average of per-feature similarities (D6, D7).

Input: candidate table (step 3), embeddings (step 4), approved evidence, `Target`, `config["weights"]` (scoring.yaml merged with the scenario's `preferences`).

Output: `score.score(...)` → score table ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)): `analog_id`, `rank`, `similarity`, `s_<feature>` for each of `text`, `atc4`, `atc3`, `area`, `line_of_therapy`, `dosing_frequency`, `n_competitors`, `order_of_entry` (NaN = not used), `n_features_used`; sorted by similarity, then `analog_id`. `rerank.rerank(scores)` is a pass-through (D4). CLI: `--until score` prints the top 10 with the breakdown.

similarity = Σ wᵢ sᵢ / Σ wᵢ, over the features both the target and the analog have (and whose weight is > 0).

Depends on: steps 1–4.

Decisions made (how each feature becomes a 0–1 score):
- **text:** cosine of the profile-text vectors, clipped to [0, 1].
- **atc4, atc3, area:** 1 if the target's code is one of the analog's codes (multi-class analogs have several), else 0; not used when the analog has no class (26 analogs).
- **line_of_therapy:** each side is sorted by keywords into *first* (no prior therapy: "no prior", "first", "1L", "initial") or *later* (after prior therapy: "after", "failed", "inadequate response", "prior", "second", "2L", "treatment-resistant"…; "untreated", "regardless of prior" count as first); 1 if the same group, else 0; not used when the text doesn't say. Only two groups, so no partial credit for an "adjacent" line. The 8 seed values and the wordings a label read may use sort as expected (tests); "adjunct" and "candidates for systemic therapy" don't say, so they're left out.
- **dosing_frequency:** both sides converted to maintenance doses per week ("once daily" 7, "every 4 weeks" 0.25; parenthetical loading or titration notes ignored; the first frequency stated wins), then 1 / (1 + |log₂ ratio|): same frequency 1, twice as often 0.5, 4× 0.33. Unparseable text ("as needed") is not used.
- **n_competitors:** 1 / (1 + |difference| / 2): 2 apart 0.5, 6 apart 0.25.
- **order_of_entry: not scored for analogs in v1.** The pool starts in 2010, so an order computed within it is wrong (Latuda would be the 1st antipsychotic, not ~9th). Its weight in scoring.yaml is 0 (decisions.md 2026-11-18); set it when label reads supply an analog value. # competitors at launch carries most of the same signal.
- **No shrinkage for few features:** an analog scored on text + class can outrank one scored on 7 features. `n_features_used` is in the table so the summary card (step 13) and the reviewer can see it. Revisit with the evaluation (step 8).
- **Ties go to `analog_id`**, so runs are reproducible. A weight of 0 means the feature isn't used (not counted in `n_features_used`). A weight for an unknown feature, or all weights 0, is an error.
- **Weights:** step 1's provisional defaults (text 1, ATC 4 0.25, ATC 3 0.25, area 0.1, line of therapy, dosing and # competitors 1), except order of entry 0 (not scored; decisions.md 2026-11-18). They change only through an evaluation result (steps 8, 9, 15).

Result on Torevia (TF-IDF, 2026-11-18): 1 Rexulti 0.681, 2 Vraylar 0.637, 3 Nuplazid 0.601, 4 Caplyta 0.585, 5 Latuda 0.465, 6 Lybalvi 0.412, then Otezla, Sotyktu, Ibrance (0.28–0.34). All 5 expected analogs are in the top 6. Nuplazid (N05AX, but Parkinson's-disease psychosis) is the kind of candidate the confirm loop's rejection is for. Otezla, Sotyktu and Ibrance score above unrelated drugs only because they have approved evidence that partly matches Torevia's profile (e.g. Otezla's 6 competitors).

Open questions:
- Should an analog with approved evidence that mismatches rank below one with no evidence at all? Today missing = left out, so evidence can only help when it matches. Decides: step 8 (evaluation).

Done when: tests cover the formula, missing features and weight overrides; Torevia's 5 known analogs rank near the top with TF-IDF. ✅ (`tests/test_score.py`; ranks 1, 2, 4, 5, 6)
