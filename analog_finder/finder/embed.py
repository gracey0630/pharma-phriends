"""Profile text and embeddings: turn each candidate and the target into comparable vectors (D6).

build_profile_text() writes one short description per drug from the same template for the target and the analogs:
  1. indication at approval (the analog's NME-compilation text; the target's `indication`): only the sentences that
     say what the drug is indicated for (trial descriptions and usage notes dilute the match), with its own brand
     name replaced by "the drug" so unique brand names don't count as a difference
  2. class names (ATC 4, ATC 3, area), without codes: codes are matched by the structured features (step 5)
  3. route group and dosage form
  4. line of therapy, dosing frequency, # competitors at launch: APPROVED evidence only for analogs (D8); left out
     on both sides while config `use_evidence` is false
A sentence whose value is missing is left out, never written as "unknown".

Embedders share one interface (fit, encode, name, cacheable). TfidfEmbedder is fitted on the analog corpus only and
then transforms the target, so changing the target never moves an analog's vector; it isn't cached because its
vectors depend on the whole corpus. It ignores the template's own label words (TEMPLATE_WORDS), so two drugs don't
look alike just because both have, say, an approved dosing sentence. RxBertEmbedder (step 9) is a fixed model: it
sets cacheable and uses EmbeddingCache, so each text is encoded once.

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


def target_text(target, names, use_evidence=True):
    """The target's profile text; class names looked up from the analogs' labels (`class_names`). Without
    use_evidence the line of therapy, dosing and # competitors sentences are left out, as they are for the analogs."""
    evidence = ([target.line_of_therapy, target.dosing_frequency,
                 "" if target.n_competitors is None else target.n_competitors] if use_evidence else ["", "", ""])
    return build_profile_text(
        target.name, target.indication_text, names.get(target.atc4, ""), names.get(target.atc3, ""),
        names.get(target.area, ""), target.route_group, target.dosage_form, *evidence)


# --- embedders ----------------------------------------------------------------------------------------------

class TfidfEmbedder:
    """TF-IDF on words and word pairs, English stop words removed, rows L2-normalized (cosine = dot product)."""
    name = "tfidf"
    cacheable = False
    center = False  # TF-IDF already down-weights words every profile shares

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


class RxBertEmbedder:
    """RxBERT (Wu et al. 2024, FDA; BioBERT further trained on prescription drug labels), a fixed model.

    Sentence vector = mean of the last hidden layer over the real tokens (attention mask), as in the RxBERT
    co-author's own embedding code; rows L2-normalized. `center`: embed() subtracts the analogs' mean vector before
    the cosine. Every profile shares a large "drug label" component, so uncentered cosines sit at 0.65-0.98 for any
    two drugs; centered, they measure what a drug shares with the target beyond the typical label. Texts are cut at 128 tokens, the length RxBERT was trained
    on (profile texts are shorter). The model loads on first use, so tests and TF-IDF runs never need torch.
    `model` / `tokenizer` can be passed in (tests use a tiny fake)."""
    name = "rxbert"
    cacheable = True
    center = True
    MAX_TOKENS = 128

    def __init__(self, model_name="seldas/rxbert-v1", model=None, tokenizer=None, batch_size=32):
        self.model_name, self.model, self.tokenizer, self.batch_size = model_name, model, tokenizer, batch_size

    def _load(self):
        if self.model is None:
            from transformers import AutoModel, AutoTokenizer
            from transformers.utils import logging
            logging.set_verbosity_error()  # the unused fill-mask head and pooler are expected, not errors
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name).eval()

    def fit(self, texts):
        return self  # a fixed model: nothing to fit

    def encode(self, texts):
        import torch
        self._load()
        texts, out = list(texts), []
        for i in range(0, len(texts), self.batch_size):
            batch = self.tokenizer(texts[i:i + self.batch_size], padding=True, truncation=True,
                                   max_length=self.MAX_TOKENS, return_tensors="pt")
            with torch.no_grad():
                hidden = self.model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            vectors = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            out.append(torch.nn.functional.normalize(vectors, dim=1).cpu().numpy())
        return np.vstack(out) if out else np.zeros((0, 0))


def get_embedder(name, config=None):
    """The embedder named in config["embedder"]: tfidf or rxbert (model from config["embedding_models"])."""
    if name == "tfidf":
        return TfidfEmbedder()
    if name == "rxbert":
        models = (config or {}).get("embedding_models") or {}
        return RxBertEmbedder(models.get("rxbert", "seldas/rxbert-v1"))
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


def embed(candidates, evidence, target, features, embedder, cache=None, use_evidence=True):
    """Vectors for the candidates and the target.

    Returns {"analog_ids": [...], "vectors": ndarray (one row per analog), "target_vector": ndarray,
             "texts": {analog_id: text}, "target_text": str}.
    The embedder is fitted on the analog texts only (the holdout, if any, is already gone from `candidates`).
    use_evidence=False (config `use_evidence`) leaves the evidence sentences out on both sides.
    An embedder with `center` (RxBERT) has the candidates' mean vector subtracted from every vector, the target's
    included; the cache keeps the raw vectors, since the mean depends on the candidate set.
    """
    texts = analog_texts(candidates, evidence if use_evidence else None)
    ids = list(texts)
    t_text = target_text(target, class_names(features), use_evidence)
    embedder.fit([texts[a] for a in ids])
    vectors = _encode(embedder, [texts[a] for a in ids], cache)
    target_vector = _encode(embedder, [t_text], cache)[0]
    if getattr(embedder, "center", False):
        mean = vectors.mean(axis=0)
        vectors, target_vector = vectors - mean, target_vector - mean
    return {"analog_ids": ids, "vectors": vectors, "target_vector": target_vector, "texts": texts,
            "target_text": t_text}


def cosine(vectors, target_vector):
    """Cosine similarity of each row with the target (0 where a vector is all zeros)."""
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(target_vector)
    with np.errstate(invalid="ignore", divide="ignore"):
        sims = vectors @ target_vector / norms
    return pd.Series(np.nan_to_num(sims), dtype=float)
