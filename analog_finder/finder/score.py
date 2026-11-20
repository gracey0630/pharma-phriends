"""Hybrid similarity: rank candidates by the weighted average of per-feature similarities (D6, D7).

    similarity = sum_i(w_i * s_i) / sum_i(w_i)   over the features both the target and the analog have

Each feature similarity s_i is in [0, 1]; a feature either side lacks (e.g. an analog with no approved line of
therapy) is left out of both sums, never scored as a mismatch. Weights come from config["weights"] (scoring.yaml,
merged with the scenario's `preferences`).

  text              cosine of the profile-text vectors (step 4), clipped to [0, 1]
  atc4, atc3, area  1 if the target's code is one of the analog's codes, else 0
  line_of_therapy   category on both sides: "first" (label limits it to untreated patients), "later" (label requires
                    prior therapy) or "any" (label sets no prior-therapy requirement); 1 if equal, else 0.
                    "not stated" is left out. Free text (approved before the categories) is read by keywords
  dosing_frequency  doses per week on both sides; 1 / (1 + |log2(ratio)|): same 1, twice as often 0.5
  n_competitors     1 / (1 + |difference| / 2): 2 apart 0.5
  order_of_entry    not scored for analogs in v1 (the pool starts in 2010, so order within it is wrong)

The evidence features (line of therapy, dosing, # competitors) are used only when config `use_evidence` is true.

Ties are broken by analog_id, so every run ranks the same way.

Spec: analog_finder/docs/components/score.md
"""
import math
import re

import numpy as np
import pandas as pd

from analog_finder.finder.embed import cosine
from analog_finder.finder.target import LINE_CATEGORIES  # first / later / any / not stated ("not stated" not scored)

FEATURES = ["text", "atc4", "atc3", "area", "line_of_therapy", "dosing_frequency", "n_competitors", "order_of_entry"]


# --- per-feature similarity -----------------------------------------------------------------------------------

def class_match(target_code, analog_codes):
    """1.0 if target_code is among the analog's '; '-separated codes, 0.0 if not, NaN if either is blank."""
    if not target_code or not isinstance(analog_codes, str) or not analog_codes.strip():
        return np.nan
    return 1.0 if target_code in [c.strip() for c in analog_codes.split(";")] else 0.0


def line_keywords(text):
    """Keyword reading of a line-of-therapy text: 'first', 'later', 'any' or None if the text doesn't say.

    Used for free-text values approved before the categories, and as a cross-check of a category against its
    label quote (line_cross_check)."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.lower()
    if re.search(r"\bno prior (?:\w+ )?(?:therapy |treatment )?(?:is )?required\b|regardless of prior", t):
        return "any"
    if re.search(r"\bno prior\b|\bnot? (?:previously )?treated\b|\buntreated\b|treatment[- ]na[iï]ve", t):
        return "first"
    if re.search(r"\bafter\b|\bfail|inadequate response|intoleran|\bprior\b|previously treated|refractory|"
                 r"resistant\b|"
                 r"\bsecond\b|\bthird\b|\b[23]l\b|\b(?:2nd|3rd)\b", t):
        return "later"
    if re.search(r"\bfirst\b|\b1l\b|\b1st\b|\binitial\b", t):
        return "first"
    return None


def line_category(value):
    """The scored category of a line-of-therapy value: 'first', 'later', 'any', or None (blank, 'not stated', or
    free text that doesn't say). A category value is taken as is; other text goes through line_keywords."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().lower()
    if v in LINE_CATEGORIES:
        return None if v == "not stated" else v
    return line_keywords(v)


def line_cross_check(category, quote):
    """The keyword reading of `quote` when it disagrees with `category`, else None (agrees, or the quote doesn't
    say). For review: a non-None result means a person should look at that value again."""
    got = line_keywords(quote)
    want = line_category(category)
    return got if got is not None and want is not None and got != want else None


_DAILY = [(r"\bfour times (?:a |per )?day|\bfour times daily|\bqid\b", 28.0),
          (r"\bthree times (?:a |per )?day|\bthree times daily|\btid\b", 21.0),
          (r"\btwice (?:a |per )?day|\btwice daily|\btwo times daily|\bbid\b", 14.0),
          (r"\bonce (?:a |per )?day|\bonce daily|\bdaily\b|\bevery day\b|\bqd\b", 7.0),
          (r"\bevery other day\b", 3.5),
          (r"\btwice (?:a |per )?week|\btwice weekly", 2.0),
          (r"\bonce (?:a |per )?week|\bonce weekly|\bweekly\b|\bevery week\b", 1.0),
          (r"\bonce (?:a |per )?month|\bmonthly\b|\bevery month\b", 7 / 30.44)]
_EVERY = re.compile(r"\bevery (\d+(?:\.\d+)?) (day|week|month)s?\b")


def doses_per_week(text):
    """Maintenance doses per week from a dosing text ('every 4 weeks (weekly loading)' -> 0.25), or None.

    Parenthetical notes (loading doses, titration) are ignored, and the first frequency stated wins, which is the
    maintenance dose in the label-read values ('twice daily (after 5-day titration)')."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = re.sub(r"\([^)]*\)", " ", text.lower())
    hits = []
    m = _EVERY.search(t)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        hits.append((m.start(), {"day": 7 / n, "week": 1 / n, "month": 7 / (30.44 * n)}[unit]))
    for pattern, per_week in _DAILY:
        m = re.search(pattern, t)
        if m:
            hits.append((m.start(), per_week))
    return min(hits)[1] if hits else None


def dosing_similarity(a, b):
    pa, pb = doses_per_week(a), doses_per_week(b)
    if pa is None or pb is None:
        return np.nan
    return 1 / (1 + abs(math.log2(pa / pb)))


def _number(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def count_similarity(a, b):
    a, b = _number(a), _number(b)
    if a is None or b is None:
        return np.nan
    return 1 / (1 + abs(a - b) / 2)


def line_similarity(a, b):
    ga, gb = line_category(a), line_category(b)
    if ga is None or gb is None:
        return np.nan
    return 1.0 if ga == gb else 0.0


# --- score table ----------------------------------------------------------------------------------------------

def feature_scores(candidates, embedding, evidence, target):
    """One row per candidate (in candidate order), one `s_<feature>` column per feature (NaN where not scored)."""
    ids = list(candidates.analog_id)
    text = cosine(embedding["vectors"], embedding["target_vector"])
    text.index = embedding["analog_ids"]
    ev = (evidence.reindex(ids) if evidence is not None and len(evidence)
          else pd.DataFrame(index=pd.Index(ids, name="analog_id")))
    get = lambda col: ev[col] if col in ev else pd.Series(np.nan, index=ev.index)  # noqa: E731
    c = candidates.set_index("analog_id")
    out = pd.DataFrame(index=pd.Index(ids, name="analog_id"))
    out["s_text"] = text.reindex(ids).clip(0, 1)
    out["s_atc4"] = [class_match(target.atc4, x) for x in c.atc4]
    out["s_atc3"] = [class_match(target.atc3, x) for x in c.atc3]
    out["s_area"] = [class_match(target.area, x) for x in c.area]
    out["s_line_of_therapy"] = [line_similarity(target.line_of_therapy, x) for x in get("line_of_therapy")]
    out["s_dosing_frequency"] = [dosing_similarity(target.dosing_frequency, x) for x in get("dosing_frequency")]
    out["s_n_competitors"] = [count_similarity(target.n_competitors, x) for x in get("n_competitors_at_launch")]
    out["s_order_of_entry"] = np.nan  # no analog value in v1 (see module docstring)
    return out


EVIDENCE_FEATURES = ["line_of_therapy", "dosing_frequency", "n_competitors"]


def score(candidates, embedding, evidence, target, weights, use_evidence=True):
    """Score table (Shared contracts): analog_id, rank, similarity, s_<feature> for each feature, n_features_used;
    sorted by similarity (high first), then analog_id. use_evidence=False (config `use_evidence`) leaves the
    evidence features out (NaN), whatever their weights."""
    unknown = set(weights) - set(FEATURES)
    if unknown:
        raise ValueError(f"weights for unknown feature(s) {sorted(unknown)}; features are {FEATURES}")
    s = feature_scores(candidates, embedding, evidence, target)
    if not use_evidence:
        s[[f"s_{f}" for f in EVIDENCE_FEATURES]] = np.nan
    w = pd.Series({f: float(weights.get(f, 0.0)) for f in FEATURES})
    if w.sum() == 0:
        raise ValueError("every feature weight is 0")
    cols = [f"s_{f}" for f in FEATURES]
    used = s[cols].notna() & (w.values > 0)
    weighted = s[cols].fillna(0).mul(w.values, axis=1).where(used, 0).sum(axis=1)
    total = used.mul(w.values, axis=1).sum(axis=1)
    s["similarity"] = (weighted / total.replace(0, np.nan)).round(6)
    s["n_features_used"] = used.sum(axis=1).astype(int)
    s = s.reset_index().sort_values(["similarity", "analog_id"], ascending=[False, True], na_position="last")
    s["rank"] = range(1, len(s) + 1)
    return s[["analog_id", "rank", "similarity"] + cols + ["n_features_used"]].reset_index(drop=True)
