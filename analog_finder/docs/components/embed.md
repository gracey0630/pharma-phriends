# embed (step 4)
Purpose: turn each candidate and the target into comparable vectors, starting with the TF-IDF baseline.

Input: candidate table (step 3), approved evidence (`io.load_approved_evidence`), `Target` (step 2), `analog_features` (for class names), an embedder.

Output: `embed.embed(...)` → `{analog_ids, vectors, target_vector, texts, target_text}`; `embed.cosine(vectors, target_vector)` for step 5. `build_profile_text()`, the `Embedder` interface (`fit`, `encode`, `name`, `cacheable`), `TfidfEmbedder`, `EmbeddingCache` ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)). CLI: `--embedder tfidf --until embed` reports the vector count.

Depends on: steps 1–3; scikit-learn 1.9.1 (added to `analog_finder/requirements.txt`).

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

Open questions:
- Text similarity on Torevia (TF-IDF, `use_evidence` off): Caplyta 0.62, Rexulti 0.52, Vraylar 0.44, Latuda 0.42, Nuplazid 0.38, Lybalvi 0.33; next is 0.12. Whether RxBERT separates Nuplazid (Parkinson's psychosis) better is for step 9.

Done when: the CLI with `--embedder tfidf --until embed` reports the count; tests check the template and the cache. ✅ (`tests/test_embed.py`; "Embeddings: 213 analogs + target (tfidf)")
