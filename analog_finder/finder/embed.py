"""Profile text and embeddings: turn each candidate and the target into comparable vectors (D6).

build_profile_text() writes one short description per drug from the same template for the target and the analogs:
  1. indication at approval (the analog's NME-compilation text; the target's `indication`): only the sentences that
     say what the drug is indicated for (trial descriptions and usage notes dilute the match), with its own brand
     name replaced by "the drug" so unique brand names don't count as a difference
  2. class names (ATC 4, ATC 3, area), without codes: codes are matched by the structured features (step 5)
  3. route group and dosage form
  4. line of therapy, dosing frequency, # competitors at launch: APPROVED evidence only for analogs (D8)
A sentence whose value is missing is left out, never written as "unknown".

Embedders share one interface (fit, encode, name, cacheable). TfidfEmbedder is fitted on the analog corpus only and
then transforms the target, so changing the target never moves an analog's vector; it isn't cached because its
vectors depend on the whole corpus. It ignores the template's own label words (TEMPLATE_WORDS), so two drugs don't
look alike just because both have, say, an approved dosing sentence. Fixed-model embedders (RxBERT, step 9) set cacheable and use EmbeddingCache.

Spec: analog_finder/docs/components/embed.md
"""
import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_FILE = "analog_embeddings.npz"
# Label words of the profile template; TF-IDF ignores them so they can't make two texts look alike.
TEMPLATE_WORDS = ["class", "broader", "therapeutic", "area", "route", "dosage", "form", "line", "therapy", "dosing",
                  "competitors", "launch"]


# --- profile text -------------------------------------------------------------------------------------------

def _name(label):
    """'N05AX Other antipsychotics; N05AE Indole derivatives' -> 'Other antipsychotics; Indole derivatives'."""
    if not isinstance(label, str) or not label.strip():
        return ""
    return "; ".join(p.strip().split(" ", 1)[1] if " " in p.strip() else "" for p in label.split(";")).strip("; ")


def _clean(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value).strip()


def indication_statement(text):
    """The sentences of an indication text that say what the drug is indicated for (all of it if none do)."""
    text = _clean(text)
    sentences = re.split(r"(?<=\.)\s+(?=[A-Z])", text)
    kept = [s for s in sentences if re.search(r"indicat", s, re.IGNORECASE)]
    return " ".join(kept) if kept else text


def _sentence(label, value):
    value = _clean(value).rstrip(".")
    return f"{label}: {value}." if value else ""


def build_profile_text(brand, indication, atc4_name="", atc3_name="", area_name="", route_group="", dosage_form="",
                       line_of_therapy="", dosing_frequency="", n_competitors=""):
    """One drug's profile text. Labels may carry codes ('N05AX Other antipsychotics'); only names are written."""
    indication = indication_statement(indication)
    brand = _clean(brand)
    if brand:
        indication = re.sub(rf"\b{re.escape(brand)}\b", "the drug", indication, flags=re.IGNORECASE)
    if isinstance(n_competitors, float) and n_competitors.is_integer():
        n_competitors = int(n_competitors)
    parts = [
        indication if indication.endswith(".") or not indication else indication + ".",
        _sentence("Class", _name(atc4_name)),
        _sentence("Broader class", _name(atc3_name)),
        _sentence("Therapeutic area", _name(area_name)),
        _sentence("Route", route_group),
        _sentence("Dosage form", _clean(dosage_form).lower()),
        _sentence("Line of therapy", line_of_therapy),
        _sentence("Dosing", dosing_frequency),
        _sentence("Competitors at launch", n_competitors),
    ]
    return " ".join(p for p in parts if p)


def class_names(features):
    """{code: label} for every ATC code in analog_features (levels 4, 3 and 1), to name the target's classes."""
    names = {}
    for col in ["class_narrow", "class_broad", "therapeutic_area"]:
        for label in features[col].dropna():
            for part in str(label).split(";"):
                part = part.strip()
                if part:
                    names.setdefault(part.split()[0], part)
    return names


def analog_texts(candidates, evidence):
    """{analog_id: profile text} for the candidate table, with approved evidence (io.load_approved_evidence)."""
    ev = evidence.reindex(candidates.analog_id) if evidence is not None and len(evidence) else None
    texts = {}
    for r in candidates.itertuples(index=False):
        e = ev.loc[r.analog_id] if ev is not None else {}
        texts[r.analog_id] = build_profile_text(
            r.drug_name, r.indication_text, r.atc4_name, r.atc3_name, r.area_name, r.route_group, r.dosage_form,
            e.get("line_of_therapy", ""), e.get("dosing_frequency", ""), e.get("n_competitors_at_launch", ""))
    return texts


def target_text(target, names):
    """The target's profile text; class names looked up from the analogs' labels (`class_names`)."""
    return build_profile_text(
        target.name, target.indication_text, names.get(target.atc4, ""), names.get(target.atc3, ""),
        names.get(target.area, ""), target.route_group, target.dosage_form, target.line_of_therapy,
        target.dosing_frequency, "" if target.n_competitors is None else target.n_competitors)


# --- embedders ----------------------------------------------------------------------------------------------

class TfidfEmbedder:
    """TF-IDF on words and word pairs, English stop words removed, rows L2-normalized (cosine = dot product)."""
    name = "tfidf"
    cacheable = False

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        stop = sorted(ENGLISH_STOP_WORDS.union(TEMPLATE_WORDS))
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words=stop)

    def fit(self, texts):
        self.vectorizer.fit(list(texts))
        return self

    def encode(self, texts):
        return self.vectorizer.transform(list(texts)).toarray()


def get_embedder(name, config=None):
    """The embedder named in config["embedder"] (tfidf; rxbert arrives in step 9)."""
    if name == "tfidf":
        return TfidfEmbedder()
    if name == "rxbert":
        raise NotImplementedError("the RxBERT embedder is plan step 9; use --embedder tfidf")
    raise ValueError(f"unknown embedder '{name}' (expected tfidf or rxbert)")


# --- cache --------------------------------------------------------------------------------------------------

class EmbeddingCache:
    """Vectors saved in data/cache/analog_embeddings.npz, keyed by embedder name + a hash of the text, so an
    approval (which changes one analog's text) invalidates only that analog. For fixed-model embedders only."""

    def __init__(self, folder):
        self.path = Path(folder) / CACHE_FILE
        self.vectors = dict(np.load(self.path)) if self.path.exists() else {}
        self.dirty = False

    @staticmethod
    def key(embedder_name, text):
        return f"{embedder_name}:{hashlib.sha1(text.encode()).hexdigest()}"

    def get(self, embedder_name, text):
        return self.vectors.get(self.key(embedder_name, text))

    def put(self, embedder_name, text, vector):
        self.vectors[self.key(embedder_name, text)] = np.asarray(vector)
        self.dirty = True

    def save(self):
        if self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.path, **self.vectors)
            self.dirty = False


def _encode(embedder, texts, cache):
    if cache is None or not embedder.cacheable:
        return embedder.encode(texts)
    missing = [t for t in texts if cache.get(embedder.name, t) is None]
    if missing:
        for t, v in zip(missing, embedder.encode(missing)):
            cache.put(embedder.name, t, v)
        cache.save()
    return np.vstack([cache.get(embedder.name, t) for t in texts])


def embed(candidates, evidence, target, features, embedder, cache=None):
    """Vectors for the candidates and the target.

    Returns {"analog_ids": [...], "vectors": ndarray (one row per analog), "target_vector": ndarray,
             "texts": {analog_id: text}, "target_text": str}.
    The embedder is fitted on the analog texts only (the holdout, if any, is already gone from `candidates`).
    """
    texts = analog_texts(candidates, evidence)
    ids = list(texts)
    t_text = target_text(target, class_names(features))
    embedder.fit([texts[a] for a in ids])
    vectors = _encode(embedder, [texts[a] for a in ids], cache)
    return {"analog_ids": ids, "vectors": vectors, "target_vector": _encode(embedder, [t_text], cache)[0],
            "texts": texts, "target_text": t_text}


def cosine(vectors, target_vector):
    """Cosine similarity of each row with the target (0 where a vector is all zeros)."""
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(target_vector)
    with np.errstate(invalid="ignore", divide="ignore"):
        sims = vectors @ target_vector / norms
    return pd.Series(np.nan_to_num(sims), dtype=float)
