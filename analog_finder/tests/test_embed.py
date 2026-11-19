import numpy as np
import pandas as pd
import pytest

from analog_finder.finder import embed, filters


def test_profile_text_template_and_brand_replacement():
    text = embed.build_profile_text(
        "Latuda", "LATUDA is indicated for schizophrenia", "N05AE Indole derivatives", "N05A ANTIPSYCHOTICS",
        "N NERVOUS SYSTEM", "oral", "TABLET, FILM COATED", "after one generic", "once daily", 6.0)
    assert text == ("the drug is indicated for schizophrenia. Class: Indole derivatives. Broader class: ANTIPSYCHOTICS. "
                    "Therapeutic area: NERVOUS SYSTEM. Route: oral. Dosage form: tablet, film coated. "
                    "Line of therapy: after one generic. Dosing: once daily. Competitors at launch: 6.")


def test_missing_values_drop_their_sentence():
    text = embed.build_profile_text("X", "X treats migraine.", route_group="oral", line_of_therapy=np.nan,
                                    dosing_frequency=None, n_competitors="")
    assert text == "the drug treats migraine. Route: oral."
    assert "unknown" not in text


def test_multi_class_names():
    assert embed._name("G03AA Progestogens; G03CA Natural estrogens") == "Progestogens; Natural estrogens"


def test_approved_evidence_reaches_analog_text(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    ev = pd.DataFrame({"line_of_therapy": ["no prior therapy required"], "dosing_frequency": [np.nan],
                       "n_competitors_at_launch": ["3"]}, index=pd.Index(["o01_oral"], name="analog_id"))
    texts = embed.analog_texts(c, ev)
    assert "Line of therapy: no prior therapy required." in texts["o01_oral"]
    assert "Competitors at launch: 3." in texts["o01_oral"]
    assert "Dosing" not in texts["o01_oral"] and "Line of therapy" not in texts["o02_oral"]


def test_use_evidence_off_drops_evidence_on_both_sides(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    ev = pd.DataFrame({"line_of_therapy": ["no prior therapy required"], "dosing_frequency": ["once daily"],
                       "n_competitors_at_launch": ["3"]}, index=pd.Index(["o01_oral"], name="analog_id"))
    e = embed.embed(c, ev, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder(),
                    use_evidence=False)
    for text in [e["texts"]["o01_oral"], e["target_text"]]:
        assert not any(w in text for w in ["Line of therapy", "Dosing", "Competitors at launch"])
    on = embed.embed(c, ev, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder())
    assert "Dosing: once daily." in on["texts"]["o01_oral"] and "Dosing: once daily." in on["target_text"]


def test_target_text_uses_analog_class_names(finder_tables, schizo_target):
    names = embed.class_names(finder_tables["analog_features"])
    text = embed.target_text(schizo_target, names)
    assert "Class: Other antipsychotics." in text and "Broader class: ANTIPSYCHOTICS." in text
    assert text.startswith("the drug is indicated for the treatment of schizophrenia")


def test_tfidf_fits_on_analogs_only_and_ranks_by_meaning(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    out = embed.embed(c, None, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder())
    assert out["vectors"].shape[0] == 12 and len(out["target_vector"]) == out["vectors"].shape[1]
    sims = embed.cosine(out["vectors"], out["target_vector"])
    sims.index = out["analog_ids"]
    assert sims.idxmax() == "o01_oral"                       # same indication and class
    assert sims["o03_oral"] > sims["o07_oral"]               # schizophrenia beats diabetes
    assert ((sims >= 0) & (sims <= 1 + 1e-9)).all()


def test_target_change_does_not_move_analog_vectors(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    a = embed.embed(c, None, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder())
    other = schizo_target.__class__(**{**schizo_target.__dict__, "indication_text": "Treats gout."})
    b = embed.embed(c, None, other, finder_tables["analog_features"], embed.TfidfEmbedder())
    assert np.allclose(a["vectors"], b["vectors"])


class _CountingEmbedder:
    name = "fixed"
    cacheable = True

    def __init__(self):
        self.encoded = []

    def fit(self, texts):
        return self

    def encode(self, texts):
        self.encoded.extend(texts)
        return np.array([[len(t), 1.0] for t in texts])


def test_cache_reuses_vectors_and_invalidates_changed_text(tmp_path):
    cache = embed.EmbeddingCache(tmp_path)
    e = _CountingEmbedder()
    embed._encode(e, ["a", "bb"], cache)
    assert (tmp_path / embed.CACHE_FILE).exists()
    e2 = _CountingEmbedder()
    vectors = embed._encode(e2, ["a", "bb", "ccc"], embed.EmbeddingCache(tmp_path))  # reloaded from disk
    assert e2.encoded == ["ccc"]  # only the new text is encoded
    assert vectors.tolist() == [[1, 1], [2, 1], [3, 1]]


def test_get_embedder():
    e = embed.get_embedder("rxbert", {"embedding_models": {"rxbert": "some/model"}})
    assert isinstance(e, embed.RxBertEmbedder) and e.model_name == "some/model" and e.cacheable
    assert e.model is None  # nothing loads until the first encode
    with pytest.raises(ValueError, match="unknown embedder"):
        embed.get_embedder("bert")


class _FakeTokenizer:
    """Word i of a text -> token id i + 1; pads with 0. Records max_length."""
    def __call__(self, texts, padding, truncation, max_length, return_tensors):
        import torch
        self.max_length = max_length
        ids = [[len(w) for w in t.split()][:max_length] for t in texts]
        width = max(len(i) for i in ids)
        return {"input_ids": torch.tensor([i + [0] * (width - len(i)) for i in ids]),
                "attention_mask": torch.tensor([[1] * len(i) + [0] * (width - len(i)) for i in ids])}


class _FakeBert:
    """last_hidden_state = (word length, 1) per token, and a large value at padding (which must be ignored)."""
    def __call__(self, input_ids, attention_mask):
        import torch
        h = torch.stack([input_ids.float(), torch.ones_like(input_ids, dtype=torch.float)], dim=-1)
        h[attention_mask == 0] = 1000.0
        return type("Out", (), {"last_hidden_state": h})()


def test_rxbert_mean_pools_real_tokens_and_normalizes():
    e = embed.RxBertEmbedder(model=_FakeBert(), tokenizer=_FakeTokenizer(), batch_size=1)
    v = e.encode(["ab abcd", "abc"])  # means (3, 1) and (3, 1); padding never enters
    expected = np.array([3, 1]) / np.linalg.norm([3, 1])
    assert np.allclose(v, [expected, expected])
    assert e.tokenizer.max_length == 128  # RxBERT's training length
    assert e.fit(["x"]) is e


def test_rxbert_vectors_are_cached(tmp_path, finder_tables, schizo_target):
    calls = []

    class Counting(embed.RxBertEmbedder):
        def encode(self, texts):
            calls.append(len(list(texts)))
            return super().encode(texts)

    c = filters.candidates(finder_tables, schizo_target)
    cache = embed.EmbeddingCache(tmp_path)
    e = Counting(model=_FakeBert(), tokenizer=_FakeTokenizer())
    embed.embed(c, None, schizo_target, finder_tables["analog_features"], e, cache)
    embed.embed(c, None, schizo_target, finder_tables["analog_features"], e, cache)
    assert calls == [len(c), 1]  # first run: the analogs, then the target; second run: all from the cache


def test_rxbert_vectors_are_centered_on_the_candidates(tmp_path, finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    e = embed.RxBertEmbedder(model=_FakeBert(), tokenizer=_FakeTokenizer())
    out = embed.embed(c, None, schizo_target, finder_tables["analog_features"], e)
    raw = e.encode([out["texts"][a] for a in out["analog_ids"]])
    assert np.allclose(out["vectors"].mean(axis=0), 0, atol=1e-6)  # the typical label is removed
    assert np.allclose(out["target_vector"], e.encode([out["target_text"]])[0] - raw.mean(axis=0))
    tfidf = embed.embed(c, None, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder())
    assert (tfidf["vectors"] >= 0).all()  # TF-IDF is not centered


def test_indication_statement_keeps_indicated_sentences():
    text = ("LATUDA is indicated for the treatment of patients with schizophrenia. The efficacy of LATUDA was "
            "established in four 6-week studies. Physicians should re-evaluate long-term use.")
    assert embed.indication_statement(text) == "LATUDA is indicated for the treatment of patients with schizophrenia."
    assert embed.indication_statement("Treats gout. In adults.") == "Treats gout. In adults."  # none say "indicated"


def test_template_words_alone_dont_make_texts_similar():
    e = embed.TfidfEmbedder().fit(["Treats gout. Line of therapy: first. Dosing: weekly.",
                                   "Treats asthma. Line of therapy: second. Dosing: daily.", "Treats acne."])
    assert "line" not in e.vectorizer.vocabulary_ and "dosing" not in e.vectorizer.vocabulary_
