# Retrieval diversity: raw top-k vs. MMR

Sampled 50 queries from the pool corpus.

- Mean pairwise cosine similarity, raw top-8: 0.790
- Mean pairwise cosine similarity, MMR-diversified top-3 (λ=0.5): 0.764

Lower is more diverse. The raw top-k for this corpus tends to be near-copies of the same generic thread; MMR trades a little pure relevance for materially less redundant exemplars.
