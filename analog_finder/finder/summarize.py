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
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pandas as pd

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


# Fact check (PR #17 review). Names: a known drug or company name that isn't in the facts fails, in any case and
# anywhere; so does a capitalized word in mid-sentence that isn't in the facts (the first word of a sentence or
# bullet may be capitalized). Numbers: each whole number must be a number of the facts, rounded to the text's own
# decimals (0.523 -> 0.52 or 0.5; within half a unit of the last digit) or as a percentage (52%); a whole number
# only stands for a fact of 1 or more, or an exact whole number, so 0.52 can't become "1".
# Words that may be capitalized mid-sentence without being in the facts: sources and terms the card is about.
CAPS_OK = {"atc", "fda", "us", "u.s", "medicaid", "medicare", "sdud", "bass", "trx", "rx", "nme", "bla", "nda"}
# Parts of company names that aren't names (sponsor names in the pool are upper case: "OTSUKA PHARMACEUTICAL CO LTD")
COMPANY_WORDS = {"pharmaceutical", "pharmaceuticals", "pharma", "pharms", "pharmaceutica", "therapeutics", "inc",
                 "llc", "ltd", "co", "corp", "corporation", "company", "laboratories", "labs", "sciences", "science",
                 "holdings", "international", "usa", "america", "americas", "global", "group", "research",
                 "development", "products", "healthcare", "health", "medical", "biologics", "biopharma", "biotech",
                 "bio", "oncology", "north", "and", "the", "of", "plc", "ag", "sa", "gmbh", "kk", "lp", "ireland",
                 "uk", "us", "division", "sub", "subsidiary", "unit", "operations", "worldwide", "specialty"}
# Salts and plain words in Drugs@FDA ingredient names, which say nothing about a particular drug
SALT_WORDS = {"sodium", "potassium", "calcium", "magnesium", "hydrochloride", "hcl", "sulfate", "acetate",
              "citrate", "phosphate", "chloride", "acid", "water", "maleate", "tartrate", "mesylate", "besylate",
              "bromide", "succinate", "fumarate", "oxide", "hydrobromide", "monohydrate", "dihydrate", "anhydrous",
              "extended", "release", "injection", "tablets", "dextrose", "oxygen", "alcohol", "lactate", "zinc",
              "iron", "hydroxide", "carbonate", "bicarbonate", "nitrate", "gluconate", "dipropionate", "propionate",
              "hydrate", "free", "base", "complex", "kit", "solution", "oral", "topical", "and", "in", "with"}
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])(?:Q)?(\d+(?:\.\d+)?)(%?)(?!\d)")
_ATC_LEVEL = re.compile(r"\bATC\s*$", re.IGNORECASE)


def _norm(word):
    w = word.replace("’", "'").lower().strip("'-")
    return w[:-2] if w.endswith("'s") else w


def _name_tokens(value, drop=frozenset(), min_len=4):
    return {w for w in (_norm(t) for t in re.split(r"[^A-Za-z'\-]+", str(value or ""))) if len(w) >= min_len
            and w not in drop and w not in _STOP}


@lru_cache(maxsize=4)
def known_names(processed=None, raw=None):
    """Drug and company names the fact check knows: {'drugs': ..., 'companies': ...}, lower case.

    From candidate_pool.csv (brand, generic, sponsor) and, when it's on this machine, Drugs@FDA's Products.txt
    (brand names and active ingredients; data/raw/ is gitignored, so not every machine has it). Drugs@FDA words that
    the pool's indications or dosage forms use are left out: they're disease or form words."""
    from pipeline.common import PROCESSED, RAW
    processed, raw = Path(processed or PROCESSED), Path(raw or RAW)
    drugs, companies, vocab = set(), set(), set()
    pool = processed / "candidate_pool.csv"
    if pool.exists():
        p = pd.read_csv(pool, dtype=str, keep_default_na=False)
        for col in ("indication", "dosage_form"):  # disease and form words: never names
            for v in p.get(col, []):
                vocab |= {_norm(t) for t in _WORD.findall(v)}
        for col in ("brand_name", "generic_name"):
            for v in p.get(col, []):
                drugs |= _name_tokens(v, SALT_WORDS)
        for v in p.get("sponsor", []):
            companies |= _name_tokens(v, COMPANY_WORDS)
    products = raw / "drugsfda" / "unzipped" / "Products.txt"
    if products.exists():
        d = pd.read_csv(products, sep="\t", dtype=str, keep_default_na=False, encoding="latin-1",
                        usecols=["DrugName", "ActiveIngredient"], on_bad_lines="skip")
        for v in pd.concat([d.DrugName, d.ActiveIngredient]).unique():  # product names include "ARTHRITIS PAIN"
            drugs |= _name_tokens(v, SALT_WORDS | BOILERPLATE | vocab, min_len=5)
    return {"drugs": frozenset(drugs), "companies": frozenset(companies - drugs)}


def _fact_words(f):
    words = set()
    for v in _strings(f):
        for t in _WORD.findall(v):
            w = _norm(t)
            words.add(w)
            words.update(_norm(part) for part in w.split("-"))
    return words


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def _fact_numbers(f, out=None):
    out = set() if out is None else out
    if isinstance(f, dict):
        for v in f.values():
            _fact_numbers(v, out)
    elif isinstance(f, (list, tuple)):
        for v in f:
            _fact_numbers(v, out)
    elif isinstance(f, bool) or f is None:
        pass
    elif isinstance(f, (int, float)):
        if f == f:
            out.add(Decimal(repr(f)))
    elif isinstance(f, str):
        out.update(Decimal(n) for n, _ in _NUMBER.findall(f))
    return out


def _rounds_to(fact, text, decimals):
    """fact rounds to text at text's decimals: within half a unit of its last digit, either way at the boundary
    (a fact stored as 0.075 may be written 0.07 or 0.08: the template's own 0.0746 -> 0.075 -> "0.07")."""
    if decimals == 0 and abs(fact) < 1 and fact != fact.to_integral_value():
        return False  # 0.52 isn't "1"
    return abs(fact - text) <= Decimal(5).scaleb(-decimals - 1)


def number_ok(text_number, percent, numbers):
    """A number written in the text stands for one of the facts' numbers (rounded, or as a percentage)."""
    t = Decimal(text_number)
    d = len(text_number.split(".")[1]) if "." in text_number else 0
    return any(_rounds_to(n, t, d) or (percent and _rounds_to(n * 100, t, d)) for n in numbers)


def _sentences(body):
    """The text's sentences: the headline and each bullet, split at sentence ends."""
    for part in [body.get("headline", "")] + list(body.get("similarities", [])) + list(body.get("differences", [])):
        yield from (x for x in re.split(r"(?<=[.!?;])\s+", str(part)) if x.strip())


def fact_check(body, f, names=None):
    """Problems with model text: numbers, drug or company names, and mid-sentence capitalized words that aren't in
    the facts. [] = passes. names: known_names() (default: from data/processed and, if present, Drugs@FDA)."""
    names = known_names() if names is None else names
    words, numbers = _fact_words(f), _fact_numbers(f)
    problems = []
    for sentence in _sentences(body):
        for m in _NUMBER.finditer(sentence):
            num, pct = m.groups()
            if _ATC_LEVEL.search(sentence[:m.start()]) and num in {"1", "2", "3", "4", "5"}:
                continue  # "ATC 4 class"
            if not number_ok(num, pct, numbers):
                problems.append(f"number {num}{pct} not in the facts")
        for i, m in enumerate(_WORD.finditer(sentence)):
            token, w = m.group(), _norm(m.group())
            if w in words:
                continue
            if w in names.get("drugs", ()) or (token[0].isupper() and w in names.get("companies", ())):
                problems.append(f"name {token} not in the facts")
            elif token[0].isupper() and i > 0 and w not in CAPS_OK and w not in _STOP:
                problems.append(f"name {token} not in the facts")
    return list(dict.fromkeys(problems))


def cache_key(f, model):
    """Card cache key: the model, the prompt and schema, and the facts, so a new model or prompt writes new cards."""
    text = "\x1f".join([model, PROMPT, json.dumps(SCHEMA, sort_keys=True), _fact_text(f)])
    return hashlib.sha1(text.encode()).hexdigest()[:12]


class Summarizer:
    """Builds cards with one setting for the run. mode: template | gemini | auto (gemini only with a key).

    llm: an object with generate_json (default llm.get_llm()); cache_dir: where Gemini cards are cached."""

    def __init__(self, mode="template", llm=None, cache_dir=None, scenario="", names=None):
        if mode not in MODES:
            raise SummaryError(f"summaries must be one of {MODES}, got {mode!r}")
        self.scenario = scenario
        self.names = names  # known_names() by default, loaded on the first model card
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
        key = cache_key(f, getattr(self.llm, "name", "model"))
        path = (self.cache_dir / "cards" / (self.scenario or "default") / f"{f['analog_id']}-{key}.json"
                if self.cache_dir else None)
        if path is not None and path.exists():
            return json.loads(path.read_text())
        try:
            body = self.llm.generate_json(PROMPT.format(facts=_fact_text(f)), SCHEMA)
        except Exception as e:  # any model failure falls back to the facts-only card
            return _card(f, template_card(f), f"template (model call failed: {type(e).__name__})")
        problems = fact_check(body, f, self.names)
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
