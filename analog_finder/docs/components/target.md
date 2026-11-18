# target (step 2)
Purpose: load the drug being forecast from its scenario file and check it has what the finder needs.

Input: `analog_finder/scenarios/<scenario>.yaml`, `target:` block. Keys follow the `target_drug` table in [data_model.md](../../../docs/data_model.md#scenario-and-output-tables-created-per-forecast); `preferences` (feature weights) sits at the top level of the scenario, as in step 1.

Output: `target.load_target(scenario) -> Target` ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)): `name`, `indication_text`, `atc4`, `atc3`, `area`, `route_group`, `dosage_form`, `line_of_therapy`, `dosing_frequency`, `n_competitors`, `order_of_entry`, `is_estimate`, `preferences`, plus `extra` (the descriptive fields the finder doesn't score, e.g. `launch_date`, `efficacy_safety_vs_soc`). A bad profile raises `TargetError` naming the field.

Depends on: step 1 (`io.load_scenario`).

Decisions made:
- **Required:** `name`, `indication`, `class_narrow` (ATC 4), `route_group`. Everything else is optional; a missing optional field is simply not scored (step 5).
- **Names:** the YAML uses the data_model.md names (`class_narrow`, `entry_order`, `n_competitors_at_launch`); `Target` uses the contract names (`atc4`, `order_of_entry`, `n_competitors`). The mapping lives only in `target.py`.
- **Class codes:** `class_narrow` may be a code (`N05AX`) or a label (`N05AX Other antipsychotics`); only the code is kept. `class_broad` and `therapeutic_area` are derived from it (first 4 characters, first character) when not given, and must agree with it when given.
- **Route group** must be `oral` or `sc`, the same route groups the pipeline gives analogs, so the route filter can't silently drop every match.
- **Pre-launch estimates allowed:** `n_competitors_at_launch` and `entry_order` are numbers ≥ 0 and carry `is_estimate` (default true).
- **Unknown keys are errors**, as in step 1, so a typo fails instead of being ignored.
- **Torevia's profile** is copied from [example_drug.md](../../../docs/example_drug.md). Its indication sentence is written in the style of the analogs' NME-compilation text ("TOREVIA is indicated for …"), so the text similarity compares like with like.

Open questions:
- Which "first" (`first_definition`) feeds scoring is still the user-journey open question; it's stored in `extra`, not scored. Decides: team.

Done when: Torevia loads; a bad or missing required field fails with a clear message; tests cover both. ✅ (`tests/test_target.py`)
