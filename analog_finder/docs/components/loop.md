# loop (step 6)
Purpose: the D3 confirm loop as plain code: show the top k, confirm or reject each, a rejection offers the next-ranked candidate; shared by the CLI now and the app's finder page (step 14).

Input: the score table (step 5), the scenario name, `config["top_k"]`.

Output: `loop.CandidateQueue` (`open`, `confirmed`, `rejected`, `remaining`, `can_stop`, `done`; `confirm`, `reject`, `restore`, `auto_confirm`, `to_frame`, `from_log`) and the decision log ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)), written as `data/scenarios/<scenario>/analog_recommendations.csv`: `scenario`, `analog_id`, `rank`, `similarity`, `decision` (shown / confirmed / rejected), `reason`, `decided_by`, `decided_at`. CLI: `python -m analog_finder.finder --scenario torevia [--auto-confirm | --resume] [--decided-by NAME]`.

Depends on: steps 1–5.

Decisions made:
- **Every event is a row**, including each candidate being shown, so the log shows what the forecaster saw and in what order, not only the outcome.
- **Reject reasons:** a fixed list plus free text, stored as `<key>` or `<key>: <note>`: `indication` (different indication or patients), `line` (different line of therapy), `distorted` (distorted curve: label expansion / generic), `data` (data quality), `other` (note required). Easy to count later; the note keeps the detail.
- **Stopping:** the forecaster may stop once 3 are confirmed (D3: 3–5). Otherwise the loop ends when every shown candidate is decided, which is 5 confirmed unless candidates run out.
- **Running out:** a rejection with no candidates left warns and offers nothing; `restore(analog_id)` brings a rejected analog back (logged as `shown` with reason `restored`).
- **Resume:** `--resume` replays the saved log on the same scores and continues; the saved rows are kept as they were. A log naming an analog that isn't a candidate now (e.g. a different holdout) is an error, not a silent mismatch. The CLI saves after every decision, so an interrupted session can resume.
- **Holdout runs write elsewhere:** with `--holdout`, outputs go to `data/scenarios/<scenario>-holdout-<ids>/` (gitignored), so evaluation runs never overwrite the committed demo outputs.
- **`decided_by`** defaults to `forecaster` (`--decided-by` to set a name); auto-confirm records `auto`. The CLI doesn't read the OS user name, so nobody's login lands in a committed file by accident.

Open questions:
- Whether the app (step 14) lets the forecaster jump to any open candidate, not only the top one. `CandidateQueue` allows any order; the CLI asks in rank order. Decides: step 14 owner.

Done when: a test rejects candidate 2 and sees candidate 6 offered; `--auto-confirm` confirms the top 5. ✅ (`tests/test_loop.py`, `tests/test_cli.py`)
