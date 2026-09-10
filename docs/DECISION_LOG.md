# Decision log

Non-obvious choices and why. Seeded before the build — **replace the bracketed guesses with what
actually happened, and add every decision you make along the way.** The brief asks for 10–15; aim
for 15 real ones. Reviewers read this file to find out whether you were thinking or following a
tutorial, so the entries that mention a number you measured are worth five that don't.

1. **Picked the brand by audit, not by volume.** Ranked 15 brands on `substantive_rate ×
   log10(volume) × (1 − template_ratio)`. The highest-volume brand had a deflection rate of
   [X]% — a corpus of non-resolutions is not groundable. Chose [BRAND] at [Y]% deflection.

2. **Rejected "similarity to the historical reply" as the quality target.** Measured that a constant
   "please DM us" string scores [X] ROUGE-L against real replies, ~[Y]% of the full system's. The
   metric mostly measures deflection, so it appears in the report only as a negative exhibit.

3. **Time-based split, not random.** Near-duplicate threads about the same incident hours apart
   leak across a random split. Quantified the gap: macro-F1 [A] random vs [B] time-ordered; the
   difference is leakage, and I report the lower number.

4. **Excluded deflection-only threads from the retrieval corpus.** You cannot ground a resolution in
   a corpus of non-resolutions. Cost: index shrank from [N] to [M] threads. Benefit:
   `unsupported_claim_rate` fell from [x]% to [y]% / drafts stopped defaulting to "DM us."

5. **Mined playbooks instead of relying on raw RAG.** Retrieval over tweets transfers *style*;
   what's needed is *procedure*. Distilled one JSON playbook per intent from ~100 historical
   resolutions. Ablation: removing playbooks cost [Δ] on groundedness.

6. **KMeans over HDBSCAN for intent induction.** Deterministic, one knob, no noise class to explain
   away. Verified stability instead: ARI [X] across 3 seeds and k ∈ {24, 30, 36}.

7. **Capped the taxonomy at 8–10 intents + `other`.** With a 200-item golden set, 20 intents means
   n≈10 per class and per-class F1 becomes noise. The taxonomy is sized to the evaluation budget,
   not to the data's apparent granularity — and that's a deliberate trade, not a shortcut.

8. **Labelled orthogonal axes, not just intent.** Routing is driven by `needs_account_access`, not
   by topic — a billing question and a login question escalate for the same structural reason. The
   axis carries the largest LR coefficient ([w]) in the risk model.

9. **The escalation threshold is calibrated, not chosen.** Split-conformal / Clopper–Pearson upper
   bound on the bad-auto-reply rate; the threshold is the largest coverage whose *upper* bound stays
   inside the risk budget, and it refuses to certify on fewer than 20 calibration points. A 0.5
   threshold is a guess; this is a guarantee with stated conditions.

10. **Kept hard rules above the learned model** for safety, legal threat, PII and prompt injection.
    Asymmetric costs deserve rules, not probabilities. [N] golden items were caught by rules the
    risk model would have auto-handled.

11. **Used self-consistency (3 samples, T=0.7) as the uncertainty signal.** No logprobs are
    available through the API, and draft disagreement turned out to be the [rank]-strongest
    escalation feature — cheaper and better-calibrated than asking the model "are you confident?",
    which is [evidence].

12. **Judge is a different model from the generator, and I measured what that doesn't fix.** Same
    family is still a bias; measured self-preference at [X], and bias-corrected the headline with
    80 human labels rather than pretending it away.

13. **Built a judge trap set before trusting the judge.** 40 replies with injected known defects.
    The judge detects invented policy at [X]% but voice drift at [Y]%, so voice is reported as
    indicative only. Knowing which dimensions of your judge are broken is worth more than a better
    judge.

14. **Committed the LLM response cache.** `make reproduce` replays it under `CORDON_OFFLINE=1`,
    so reviewers reproduce every headline number in [T] minutes with no API key and no spend — and
    a test proves the offline path never calls the API.

15. **No LangChain / no vector DB / no framework.** The whole pipeline is [N] lines of plain Python
    over numpy dot products. The brief says I'll be asked to explain and modify my own code live;
    every framework layer is a layer I would have to explain but did not write.

16. **Pre-labelled the golden set with a weak TF-IDF k-NN, never with my own agent**, and measured
    my own anchoring on a 50-item blind core ([X]% acceptance of wrong pre-labels vs. [Y]% blind
    error rate). Pre-labelling with the system under test would have made the golden set a mirror.

17. **Reported headline metrics on the `natural` stratum only.** The full 200 is deliberately
    enriched with hard cases; quoting an accuracy over it would overstate difficulty in one
    direction and understate the tail in the other.

18. **Cut [thing you cut] and said so.** [One line on the trade.] Cutting loudly beats shipping a
    half-built feature that the evaluation can't support.
