"""Summary cards: one short card per candidate saying why it ranked where it did (plan step 13).

The template card is built from the facts only (score breakdown, class names, indication words, approved evidence,
flags), so it works offline and can't state anything the data doesn't. With a Gemini key, the model may rewrite the
headline, similarities and differences from the same facts (passed as JSON); its text is checked against the facts
and the template card is used if the check fails. Breakdown, flags and sources always come from the data.

Card (Shared contracts): analog_id, drug_name, rank, similarity, headline, similarities[], differences[],
score_breakdown {feature: {score, weight}}, flags[], sources[{field, quote, url}], generated_by.

Spec: analog_finder/docs/components/summarize.md
"""
import hashlib
import json
import re
from pathlib import Path

from analog_finder.finder.embed import indication_statement
from analog_finder.finder.score import FEATURES, doses_per_week, line_similarity

MODES = ("template", "gemini", "auto")
MAX_WORDS = 6
FLAG_LABELS = {"warn_label_expansion": "possible label expansion in the first 3 years",
               "warn_multi_route": "brand has more than one route",
               "low_volume": "low Medicaid volume",
               "peak_not_confirmed": "peak not confirmed yet (share of peak is an upper bound)",
               "weak_bass_fit": "weak Bass fit"}
FEATURE_LABELS = {"text": "indication text", "atc4": "same ATC 4 class", "atc3": "same ATC 3 class",
                  "area": "same therapeutic area", "line_of_therapy": "line of therapy",
                  "dosing_frequency": "dosing frequency", "n_competitors": "# competitors at launch",
                  "order_of_entry": "order of entry"}
EVIDENCE = [("line_of_therapy", "line_of_therapy", "line of therapy"),
            ("dosing_frequency", "dosing_frequency", "dosing"),
            ("n_competitors_at_launch", "n_competitors", "# competitors at launch")]
# Indication boilerplate: says nothing about which disease or patients
BOILERPLATE = {"indicated", "indication", "indications", "treatment", "treat", "treating", "patients", "patient",
               "adult", "adults", "use", "used", "therapy", "drug", "associated", "including", "limitations",
               "disorder", "disease", "adjunctive", "adjunct", "monotherapy", "years", "older", "aged", "age",
               "moderate", "severe", "moderately", "severely", "active", "tablets", "tablet", "capsules", "oral",
               "subcutaneous", "injection", "mg", "dose", "daily", "once", "twice", "established", "efficacy"}
SCHEMA = {
    "title": "summary_card", "type": "object", "required": ["headline", "similarities", "differences"],
    "properties": {"headline": {"type": "string"},
                   "similarities": {"type": "array", "items": {"type": "string"}},
                   "differences": {"type": "array", "items": {"type": "string"}}},
}
PROMPT = """You write a short card for a pharmaceutical forecaster deciding whether a past drug launch is a good
analog for a new drug. Use ONLY the facts in the JSON below; do not add facts, drug names, companies or numbers that
are not in it. Write: a one-sentence headline saying why this analog ranked where it did; up to 4 short
similarities; up to 4 short differences. Plain words, no marketing language.

FACTS:
{facts}
"""


class SummaryError(ValueError):
    """Bad summaries setting (e.g. gemini without a key)."""


# --- words --------------------------------------------------------------------------------------------------

def _stop_words():
    try:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        return set(ENGLISH_STOP_WORDS)
    except ImportError:  # scikit-learn is in requirements; this keeps the module importable without it
        return {"the", "of", "and", "or", "for", "in", "with", "a", "an", "to", "as", "by", "on", "at", "is", "be"}


_STOP = _stop_words() | BOILERPLATE


def indication_words(text, brand=""):
    """Disease and patient words of an indication: 'indicated for' sentences, lower-case, no stop words, brand or
    boilerplate. Multi-word disease names stay one phrase where a hyphen or apostrophe joins them."""
    text = indication_statement(text).replace("’", "'").lower()
    if brand:
        text = re.sub(rf"\b{re.escape(brand.lower())}\b", " ", text)
    words = re.findall(r"[a-z][a-z'\-]*[a-z]", text)
    out = []
    for w in words:
        w = w.strip("'-")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) > 2 and w not in _STOP and w not in out:
            out.append(w)
    return out


def _display(name):
    """A class name for reading: 'ANTIPSYCHOTICS' -> 'Antipsychotics' (ATC 3 and 1 names are upper case)."""
    name = name.strip()
    return name.capitalize() if name.isupper() else name


def _names(label):
    """'N05AX Other antipsychotics; N05AE Indole derivatives' -> {'N05AX': 'Other antipsychotics', ...}."""
    out = {}
    for part in str(label or "").split(";"):
        part = part.strip()
        if part:
            code, _, name = part.partition(" ")
            out[code] = _display(name) or code
    return out


def _codes(value):
    return [c.strip() for c in str(value or "").split(";") if c.strip()]


# --- facts --------------------------------------------------------------------------------------------------

def facts(score_row, cand, target, weights, evidence=None, use_evidence=False, target_class_names=None):
    """Everything a card may say, as plain data (also what Gemini is given)."""
    s, c = dict(score_row), dict(cand)
    breakdown = {}
    for f in FEATURES:
        v, w = s.get(f"s_{f}"), float(weights.get(f, 0) or 0)
        if v == v and v is not None and w > 0:
            breakdown[f] = {"score": round(float(v), 3), "weight": w}
    t_words = indication_words(target.indication_text, target.name)
    a_words = indication_words(c.get("indication_text", ""), c.get("drug_name", ""))
    names = {"atc4": _names(c.get("atc4_name")), "atc3": _names(c.get("atc3_name")),
             "area": _names(c.get("area_name"))}
    tnames = {k: _names(v).get(k, k) for k, v in (target_class_names or {}).items()}  # code -> name, no code
    classes = {}
    for level, tcode in [("atc4", target.atc4), ("atc3", target.atc3), ("area", target.area)]:
        acodes = _codes(c.get(level))
        classes[level] = {"same": bool(tcode) and tcode in acodes, "target": tnames.get(tcode, tcode),
                          "analog": "; ".join(names[level].get(a, a) for a in acodes)}
    ev = {}
    if evidence is not None and c.get("analog_id") in getattr(evidence, "index", []):
        row = evidence.loc[c["analog_id"]]
        for field, tattr, label in EVIDENCE:
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                ev[field] = {"label": label, "analog": value.strip(), "target": _plain(getattr(target, tattr, "")),
                             "quote": row.get(f"{field}_quote", "") or "", "url": row.get(f"{field}_url", "") or ""}
    return {
        "analog_id": c.get("analog_id"), "drug_name": c.get("drug_name", ""), "target_name": target.name,
        "rank": int(s["rank"]), "similarity": round(float(s["similarity"]), 3),
        "breakdown": breakdown, "classes": classes,
        "shared_indication_words": [w for w in a_words if w in t_words][:MAX_WORDS],
        "analog_only_indication_words": [w for w in a_words if w not in t_words][:MAX_WORDS],
        "evidence": ev, "use_evidence": bool(use_evidence),
        "flags": [label for col, label in FLAG_LABELS.items() if bool(c.get(col))],
    }


def _plain(value):
    """A target value as text: None -> '', 6.0 -> '6'."""
    if value is None or value != value:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _evidence_match(field, a, t):
    if field == "line_of_therapy":
        m = line_similarity(t, a)  # the scorer's own rule: categories, keywords for older free text
        return None if m != m else m == 1
    if field == "dosing_frequency":
        pa, pt = doses_per_week(a), doses_per_week(t)
        return None if pa is None or pt is None else abs(pa - pt) < 1e-9
    try:
        return float(a) == float(t)
    except ValueError:
        return None


# --- template card ------------------------------------------------------------------------------------------

def template_card(f):
    cl, sim, diff = f["classes"], [], []
    if cl["atc4"]["same"]:
        reason = f"same ATC 4 class ({cl['atc4']['target']})"
    elif cl["atc3"]["same"]:
        reason = f"same ATC 3 class ({cl['atc3']['target']})"
    elif f["shared_indication_words"]:
        reason = "indication shares " + ", ".join(f["shared_indication_words"][:3])
    else:
        reason = "indication text only"
    headline = f"#{f['rank']} {f['drug_name']}, similarity {f['similarity']:.2f}: {reason}."

    for level, word in [("atc4", "ATC 4 class"), ("atc3", "ATC 3 class"), ("area", "therapeutic area")]:
        if cl[level]["same"]:
            sim.append(f"Same {word}: {cl[level]['target']}")
            break  # the narrowest shared level says enough
    if f["shared_indication_words"]:
        sim.append("Both indicated for: " + ", ".join(f["shared_indication_words"]))
    if "text" in f["breakdown"]:
        sim.append(f"Indication text similarity {f['breakdown']['text']['score']:.2f}")

    if not cl["atc4"]["same"] and cl["atc4"]["analog"]:
        diff.append(f"Different ATC 4 class: {cl['atc4']['analog']} (target: {cl['atc4']['target'] or 'none'})")
    elif not cl["atc4"]["analog"]:
        diff.append("No ATC class on record for this analog")
    if f["analog_only_indication_words"]:
        diff.append("Its indication also mentions: " + ", ".join(f["analog_only_indication_words"]))

    for field, e in f["evidence"].items():
        m = _evidence_match(field, e["analog"], e["target"]) if e["target"] else None
        text = f"{e['label'].capitalize()}: {e['analog']}" + (f" (target: {e['target']})" if e["target"] else "")
        if not f["use_evidence"]:
            diff.append(f"{text}; not used in matching yet")
        elif m is True:
            sim.append(text)
        elif m is False:
            diff.append(text)
    return {"headline": headline, "similarities": sim, "differences": diff}


def _card(f, body, generated_by):
    return {"analog_id": f["analog_id"], "drug_name": f["drug_name"], "rank": f["rank"],
            "similarity": f["similarity"], "headline": body["headline"],
            "similarities": list(body["similarities"]), "differences": list(body["differences"]),
            "score_breakdown": f["breakdown"], "flags": list(f["flags"]),
            "sources": [{"field": k, "quote": e["quote"], "url": e["url"]} for k, e in f["evidence"].items()
                        if e["quote"] or e["url"]],
            "generated_by": generated_by}


# --- model card ---------------------------------------------------------------------------------------------

def _fact_text(f):
    return json.dumps(f, ensure_ascii=False, sort_keys=True)


def fact_check(body, f):
    """Problems with model text: numbers not in the facts, capitalized names not in the facts. [] = passes."""
    text = " ".join([body.get("headline", "")] + list(body.get("similarities", [])) + list(body.get("differences", [])))
    known = _fact_text(f).lower()
    problems = []
    for num in re.findall(r"\d+(?:\.\d+)?", text):
        variants = {num, num.rstrip("0").rstrip(".") if "." in num else num}
        if not any(v in known for v in variants):
            problems.append(f"number {num} not in the facts")
    for name in re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", text):
        if name.lower() not in known and name not in {"Same", "Both", "Different", "Its", "This", "That", "The",
                                                      "Target", "Analog", "Indication", "Class", "Similar",
                                                      "Ranked", "Ranks", "Similarity", "Dosing", "Line", "Their",
                                                      "These", "Medicaid", "Bass", "Peak", "Also", "Unlike"}:
            problems.append(f"name {name} not in the facts")
    return problems


class Summarizer:
    """Builds cards with one setting for the run. mode: template | gemini | auto (gemini only with a key).

    llm: an object with generate_json (default llm.get_llm()); cache_dir: where Gemini cards are cached."""

    def __init__(self, mode="template", llm=None, cache_dir=None, scenario=""):
        if mode not in MODES:
            raise SummaryError(f"summaries must be one of {MODES}, got {mode!r}")
        self.scenario = scenario
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.llm = None
        if mode != "template":
            if llm is None:
                from analog_finder import llm as llm_module
                llm = llm_module.get_llm()
            if getattr(llm, "name", "") == "fake" and mode == "auto" and not getattr(llm, "fixtures", None):
                llm = None  # no key: the template card, not a skeleton answer
            elif getattr(llm, "name", "") == "fake" and mode == "gemini" and not getattr(llm, "fixtures", None):
                raise SummaryError("summaries: gemini needs GEMINI_API_KEY and GEMINI_MODEL in .env; "
                                   "use template or auto")
            self.llm = llm
        self.mode = mode

    @property
    def generator(self):
        return "template" if self.llm is None else getattr(self.llm, "name", "model")

    def card(self, score_row, cand, target, weights, evidence=None, use_evidence=False, target_class_names=None):
        f = facts(score_row, cand, target, weights, evidence, use_evidence, target_class_names)
        if self.llm is None:
            return _card(f, template_card(f), "template")
        key = hashlib.sha1(_fact_text(f).encode()).hexdigest()[:12]
        path = (self.cache_dir / "cards" / (self.scenario or "default") / f"{f['analog_id']}-{key}.json"
                if self.cache_dir else None)
        if path is not None and path.exists():
            return json.loads(path.read_text())
        try:
            body = self.llm.generate_json(PROMPT.format(facts=_fact_text(f)), SCHEMA)
        except Exception as e:  # any model failure falls back to the facts-only card
            return _card(f, template_card(f), f"template (model call failed: {type(e).__name__})")
        problems = fact_check(body, f)
        if problems:
            return _card(f, template_card(f), "template (model output failed the fact check: "
                         + "; ".join(problems[:3]) + ")")
        card = _card(f, body, getattr(self.llm, "name", "model"))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(card, ensure_ascii=False, indent=1))
        return card


def render(card, width=100):
    """Plain text for the CLI."""
    lines = [card["headline"]]
    if card["similarities"]:
        lines.append("   alike:     " + "; ".join(card["similarities"]))
    if card["differences"]:
        lines.append("   different: " + "; ".join(card["differences"]))
    if card["score_breakdown"]:
        lines.append("   scored on: " + ", ".join(f"{FEATURE_LABELS.get(k, k)} {v['score']:.2f} (weight {v['weight']:g})"
                                               for k, v in card["score_breakdown"].items()))
    if card["flags"]:
        lines.append("   flags:     " + "; ".join(card["flags"]))
    for s in card["sources"]:
        lines.append(f"   source:    {s['field']}: \"{s['quote'][:width]}\" {s['url']}")
    if card["generated_by"] != "template":
        lines.append(f"   ({card['generated_by']})")
    return "\n".join(lines)
