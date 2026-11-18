# filters (step 3)
Purpose: reduce the 426 analogs to the usable ones in the target's route group, carrying warnings, with an optional holdout.

Input: `io.load_tables()` (`analog_features`, `candidate_pool`, `analogs`, `bass_fits`), a `Target` (step 2), `config["filters"]`, `--holdout`.

Output: `filters.candidates(tables, target, filters, holdout, top_k)` → candidate table ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)), one row per candidate, sorted by `analog_id`: `analog_id`, `drug_name`, `atc4`, `atc3`, `area` (codes), `atc4_name`, `atc3_name`, `area_name` (labels, for the profile text), `route_group`, `dosage_form`, `indication_text`, and the warning flags `warn_label_expansion`, `warn_multi_route`, `low_volume`, `peak_not_confirmed`, `weak_bass_fit`. CLI: `python -m analog_finder.finder --scenario torevia --until filters [--holdout <analog_id>]`.

Depends on: steps 1–2; `pipeline/checks.py` (`usable`, `funnel_steps`).

Decisions made:
- **Usable is read from one definition, not recomputed.** The `checks.md` funnel rules moved into `pipeline.checks.funnel_steps()` / `usable()`; the funnel report and the finder both call them. The report is unchanged (still 261 usable: 213 oral, 48 sc). D2: generic entry and late launch are excluded there; nothing new is excluded here.
- **Warnings, not filters:** `warn_label_expansion` (= `label_expansion_in_window`, which over-flags), `warn_multi_route`, `low_volume`, `peak_not_confirmed` (= not `peak_confirmed`), `weak_bass_fit` (an analog with no Bass fit counts as weak).
- **Multi-class analogs** (9, mostly combination products) keep every code, `; `-separated (`G03AA; G03CA`); step 5 counts a class match if the target's code is any of them. The 26 analogs with no ATC class have blank codes.
- **Holdout is removed before filtering**, so nothing fitted later (the TF-IDF vocabulary in step 4) can see it. An unknown holdout id is an error, not a silent no-op.
- **Too few candidates:** fewer than 2 × `top_k` (the top 5 plus replacements) is a warning and the run continues; none is an error.

Open questions:
- Clinic-administered sc products are still in the sc pool (no self-administered flag yet; CLAUDE.md known issues). When the flag exists, it becomes a filter here. Decides: workstream A/D.

Done when: Latuda, Rexulti, Vraylar, Caplyta and Lybalvi pass for Torevia; `--holdout latuda_oral` removes Latuda; tests cover each flag. ✅ (`tests/test_filters.py`; 213 oral candidates for Torevia, 212 with the holdout)
