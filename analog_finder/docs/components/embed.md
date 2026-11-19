# embed (steps 4 and 9)
Purpose: turn each candidate and the target into comparable vectors, starting with the TF-IDF baseline.

Input: candidate table (step 3), approved evidence (`io.load_approved_evidence`), `Target` (step 2), `analog_features` (for class names), an embedder.

Output: `embed.embed(...)` → `{analog_ids, vectors, target_vector, texts, target_text}`; `embed.cosine(vectors, target_vector)` for step 5. `build_profile_text()`, the `Embedder` interface (`fit`, `encode`, `name`, `cacheable`, `center`), `TfidfEmbedder`, `RxBertEmbedder` (step 9), `EmbeddingCache` ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)). CLI: `--embedder tfidf --until embed` reports the vector count.

Depends on: steps 1–3; scikit-learn 1.9.1; for RxBERT, torch 2.15.0 and transformers 5.23.0 (`analog_finder/requirements.txt`) and a one-time 433 MB model download from Hugging Face.

Decisions made:
- **Template** (same for target and analogs): indication statement; class names (ATC 4, ATC 3, area); route and dosage form; then line of therapy, dosing and # competitors — approved values only for analogs (D8), the profile's values for the target. Example (Torevia): "the drug is indicated for the treatment of schizophrenia in adults. Class: Other antipsychotics. Broader class: ANTIPSYCHOTICS. Therapeutic area: NERVOUS SYSTEM. Route: oral. Dosage form: tablet. Line of therapy: …. Dosing: once daily. Competitors at launch: 6."
- **Evidence sentences only with `use_evidence` on** (off for now, decisions.md 2026-11-18): line of therapy, dosing and # competitors are left out of both the target's and the analogs' text, so the seed 8 analogs don't match on them.
- **A missing value drops its sentence**, never "unknown" (which would make every incomplete profile look alike).
- **Indication statement only:** of the NME-compilation text, only sentences mentioning "indicated" are kept (all of it if none do). Latuda's text adds trial and long-term-use boilerplate that halved its similarity to Torevia (0.17 → 0.40 with the trim).
- **Brand names → "the drug"**, in the analog's own text and the target's, so a unique brand name never counts as a difference.
- **Class names, not codes,** in the text: codes are matched by the structured features in step 5, so writing `N05AX` here would count the class twice. The target's class names are looked up from the analogs' labels, so both sides use the same words.
- **TF-IDF ignores the template's label words** (`TEMPLATE_WORDS`: "line", "therapy", "dosing", "competitors", …). Without this, the 3 oral seed analogs with approved evidence (Otezla, Sotyktu, Ibrance) ranked near the top for Torevia only because both texts had a "Dosing:" sentence.
- **TF-IDF is fitted on the analog corpus only**, then transforms the target, so a new target never moves an analog's vector. A holdout is gone before fitting. Words and word pairs, English stop words, sublinear term frequency, L2-normalized rows.
- **Cache:** `data/cache/analog_embeddings.npz`, key = embedder name + SHA-1 of the text, so an approval invalidates only that analog. Used only by fixed-model embedders (`cacheable`); TF-IDF vectors depend on the whole corpus and take under a second, so they aren't cached.

**RxBERT (step 9)** — `seldas/rxbert-v1` (Wu et al. 2024, FDA: BioBERT further trained on prescription drug labels). License: none stated; used on the reasoning in decisions.md (2026-11-18).
- **Sentence vector:** mean of the last hidden layer over the real tokens (not the CLS token), as in the RxBERT co-author's own embedding code (`magnus-gray/Embedding4Tox`); L2-normalized.
- **Length:** texts cut at 128 tokens, the length RxBERT was trained on; profile texts are shorter, so nothing is lost.
- **Centering:** every profile shares a large "drug label" component, so uncentered cosines sit at 0.65–0.98 for any two drugs (Torevia: median candidate 0.85). That squashes the text feature and lets analogs with no ATC class (scored on text alone) outrank same-area drugs. `embed()` subtracts the candidates' mean vector from every vector, the target's included, so the cosine measures what a drug shares with the target beyond the typical label (Torevia: median 0, max 0.91, the same shape as TF-IDF). The mean is over the candidates only, so a held-out analog never shapes it. Decided before the evaluation; uncentered RxBERT isn't evaluated.
- **Loading:** on first encode only, so tests and TF-IDF runs never import torch. The fill-mask head and the pooler in the checkpoint are unused (warnings silenced). The weights are a pickle (`pytorch_model.bin`); loading one runs code from the file, an accepted risk for this research model.
- **Cache:** raw vectors in `data/cache/analog_embeddings.npz` (centering depends on the candidate set, so it's applied after). Each text is encoded once; the first Torevia run takes ~15 s, then seconds.

Torevia check (`use_evidence` off), text similarity. TF-IDF: Caplyta 0.62, Rexulti 0.52, Vraylar 0.44, Latuda 0.42, Nuplazid 0.38, Lybalvi 0.33; next 0.12. RxBERT (centered): Latuda 0.91, Caplyta 0.89, Rexulti 0.81, Nuplazid 0.79, Vraylar 0.77, Lybalvi 0.57 (below two antidepressants, Viibryd 0.67 and Brintellix 0.65; its class matches keep it 6th overall). Neither embedder separates Nuplazid (Parkinson's psychosis); the confirm loop does.

Open questions: none.

Done when: the CLI with `--embedder tfidf --until embed` reports the count; tests check the template and the cache. ✅ (`tests/test_embed.py`; "Embeddings: 213 analogs + target (tfidf)")
Step 9 done when: the evaluation table includes RxBERT; `scoring.yaml` defaults set from it, numbers in `decisions.md`. Tests (offline, a fake model): mean pooling over real tokens, 128-token cut, cache, centering.
