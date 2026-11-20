"""The target drug: the brand being forecast, read from the `target:` block of a scenario YAML.

Keys in the YAML follow the `target_drug` table in docs/data_model.md (class_narrow, entry_order,
n_competitors_at_launch, ...). The `Target` record uses the names in the plan's Shared contracts (atc4, atc3, area,
order_of_entry, n_competitors), which the rest of the finder reads.

Required: name, indication, class_narrow (ATC 4), route_group. class_broad (ATC 3) and therapeutic_area (ATC 1) are
derived from the ATC 4 code when not given. line_of_therapy, when given, is one of first / later / any / not stated
(what the target's label says about prior therapy). Pre-launch numbers (# competitors, order of entry) are estimates for a
target, so they carry is_estimate (default true).

Spec: analog_finder/docs/components/target.md
"""
import re
from dataclasses import dataclass, field

from analog_finder import io

ROUTE_GROUPS = ("oral", "sc")  # the pipeline's in-scope route groups (decisions.md 2026-10-21)
# line_of_therapy categories, on the label basis (decisions.md 2026-11-19); score.py reads them from here
LINE_CATEGORIES = ("first", "later", "any", "not stated")
ATC4 = re.compile(r"^[A-Z]\d{2}[A-Z]{2}$")  # e.g. N05AX

REQUIRED = ["name", "indication", "class_narrow", "route_group"]
OPTIONAL = ["target_patient_definition", "class_broad", "therapeutic_area", "dosage_form", "line_of_therapy",
            "entry_order", "first_definition", "expected_n_entrants", "n_competitors_at_launch", "is_estimate",
            "efficacy_safety_vs_soc", "dosing_frequency", "days_supply", "dosing_vs_alternatives", "launch_date"]


class TargetError(ValueError):
    """The scenario's target profile is missing a required field or has a bad value."""


@dataclass
class Target:
    name: str
    indication_text: str
    atc4: str
    atc3: str
    area: str
    route_group: str
    dosage_form: str = ""
    line_of_therapy: str = ""
    dosing_frequency: str = ""
    n_competitors: float | None = None
    order_of_entry: int | None = None
    is_estimate: bool = True
    preferences: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)  # the descriptive target_drug fields the finder doesn't score


def _code(value):
    """'N05AX Other antipsychotics' or 'N05AX' -> 'N05AX'."""
    return str(value).strip().split()[0].upper() if str(value).strip() else ""


def _number(spec, key, kind):
    value = spec.get(key)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise TargetError(f"target.{key}: expected a number, got {value!r}")
    try:
        number = kind(value)
    except (TypeError, ValueError):
        raise TargetError(f"target.{key}: expected a number, got {value!r}") from None
    if number < 0:
        raise TargetError(f"target.{key}: must be >= 0, got {value!r}")
    return number


def from_dict(spec, preferences=None):
    """Build and check a Target from the scenario's `target:` mapping."""
    if not isinstance(spec, dict):
        raise TargetError("scenario has no `target:` block (see analog_finder/scenarios/torevia.yaml)")
    unknown = set(spec) - set(REQUIRED) - set(OPTIONAL)
    if unknown:
        raise TargetError(f"target: unknown field(s) {sorted(unknown)} (known: {', '.join(REQUIRED + OPTIONAL)})")
    missing = [k for k in REQUIRED if not str(spec.get(k) or "").strip()]
    if missing:
        raise TargetError(f"target: missing required field(s) {missing}")

    atc4 = _code(spec["class_narrow"])
    if not ATC4.match(atc4):
        raise TargetError(f"target.class_narrow: expected an ATC level 4 code such as N05AX, got {spec['class_narrow']!r}")
    atc3 = _code(spec.get("class_broad") or atc4[:4])
    area = _code(spec.get("therapeutic_area") or atc4[0])
    if atc3 != atc4[:4] or area != atc4[0]:
        raise TargetError(f"target: class_broad {atc3} / therapeutic_area {area} don't contain class_narrow {atc4}")
    route = str(spec["route_group"]).strip().lower()
    if route not in ROUTE_GROUPS:
        raise TargetError(f"target.route_group: expected one of {ROUTE_GROUPS}, got {spec['route_group']!r}")
    line = str(spec.get("line_of_therapy") or "").strip().lower()
    if line and line not in LINE_CATEGORIES:
        raise TargetError(f"target.line_of_therapy: expected one of {LINE_CATEGORIES} (what the label says about "
                          f"prior therapy; practice patterns go in target_patient_definition), "
                          f"got {spec['line_of_therapy']!r}")
    is_estimate = spec.get("is_estimate", True)
    if not isinstance(is_estimate, bool):
        raise TargetError(f"target.is_estimate: expected true or false, got {is_estimate!r}")

    scored = {"name", "indication", "class_narrow", "class_broad", "therapeutic_area", "route_group", "dosage_form",
              "line_of_therapy", "dosing_frequency", "n_competitors_at_launch", "entry_order", "is_estimate"}
    return Target(
        name=str(spec["name"]).strip(),
        indication_text=str(spec["indication"]).strip(),
        atc4=atc4, atc3=atc3, area=area, route_group=route,
        dosage_form=str(spec.get("dosage_form") or "").strip(),
        line_of_therapy=line,
        dosing_frequency=str(spec.get("dosing_frequency") or "").strip(),
        n_competitors=_number(spec, "n_competitors_at_launch", float),
        order_of_entry=_number(spec, "entry_order", int),
        is_estimate=is_estimate,
        preferences=dict(preferences or {}),
        extra={k: v for k, v in spec.items() if k not in scored},
    )


def load_target(scenario, scenarios_dir=None):
    """The scenario's Target (analog_finder/scenarios/<scenario>.yaml, `target:` block)."""
    spec = io.load_scenario(scenario, scenarios_dir)
    try:
        return from_dict(spec.get("target"), spec.get("preferences"))
    except TargetError as e:
        raise TargetError(f"{scenario}.yaml: {e}") from None
