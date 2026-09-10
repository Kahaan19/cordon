# Citations

Everything borrowed — a paper, a metric definition, a prompt pattern, a snippet, a model card —
recorded at the moment it's borrowed. BUILD_SPEC.md §1 grades this explicitly.

## Data

- **Customer Support on Twitter** (`thoughtvector/customer-support-on-twitter`, Kaggle).
  Licence: **CC-BY-NC-SA-4.0** — non-commercial, share-alike, attribution required. This repo's
  use (a take-home evaluation submission) is non-commercial. `data/raw/` is gitignored; nothing
  from the raw corpus is committed verbatim except derived artifacts explicitly called out as
  committed in BUILD_SPEC.md §11 (golden set rows with tweet IDs + labels, embeddings, aggregate
  stats) — consistent with a share-alike, non-commercial licence.

## Models

- **BAAI/bge-small-en-v1.5** (Hugging Face model card). Fixed embedding model project-wide
  (BUILD_SPEC.md §2). The model card recommends prefixing *queries* with the instruction
  `"Represent this sentence for searching relevant passages: "` for asymmetric retrieval; applied
  uniformly to every embedded message here (clustering, not retrieval) per BUILD_SPEC.md §5 step 2.
- **KMeans clustering stability via re-induction + Adjusted Rand Index** — standard clustering
  stability methodology (compare partitions of the same point set under different random
  inits/k), applied per BUILD_SPEC.md §5 to the taxonomy induction.
