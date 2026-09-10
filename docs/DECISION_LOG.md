# Decision log

Non-obvious choices and why. Seeded before the build — **replace the bracketed guesses with what
actually happened, and add every decision you make along the way.** The brief asks for 10–15; aim
for 15 real ones. Reviewers read this file to find out whether you were thinking or following a
tutorial, so the entries that mention a number you measured are worth five that don't.

1. **Picked the brand by audit, not by volume.** Ranked the top 15 brands by volume on
   `substantive_rate × log10(n_threads) × (1 − template_ratio)`. The highest-volume brand
   (AmazonHelp, 81,454 threads) has deflection_rate 5.9% and substantive_rate 43.3% — lower
   deflection than BUILD_SPEC.md §4 predicted ("well north of 50%"), because Amazon's dominant
   first-reply pattern is a public diagnostic question with no resolution and no off-platform
   redirect language at all, not a literal "DM us" (see #21 — that's the report's headline
   surprise, not a deflection-regex bug). Picked **hulu_support** instead: 14,790 threads,
   deflection_rate 1.2%, substantive_rate 61.1%, answerability_score 1.584 vs. AmazonHelp's
   1.030 — real troubleshooting content in public (device models, network requirements,
   power-cycle steps), not privacy-gated handoffs.

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

19. **Used TF-IDF, not bge-small, for the audit's `topic_entropy` KMeans.** `topic_entropy` is
    descriptive flavor in `brand_audit.md` ("a brand with one topic is a boring brand") and is not
    a term in `answerability_score` — the pick doesn't depend on it. Loading the project's fixed
    neural embedding model this early, before it's load-bearing (taxonomy induction, Phase 2), was
    a heavier dependency than the number's importance justified. Confirmed on a synthetic 12,020-
    thread smoke test that the pipeline still correctly separates a deflecting brand from a
    substantive one on the metrics that matter (`substantive_rate`, `deflection_rate`); revisit if
    a reviewer wants topic_entropy on the fixed embedding for consistency with later phases.

20. **`requires-python = ">=3.11"`, not pinned to 3.11 exactly.** BUILD_SPEC.md §2 names Python
    3.11; this machine only has 3.13 system-wide. Let `uv sync` resolve its own interpreter rather
    than assuming one exists — it picked 3.12, which satisfies every constraint in the spec (MPS
    support, dependency compatibility) without a manual `uv python install 3.11` step.

21. **Widened `DEFLECTION_PATTERNS` after auditing real AmazonHelp replies, then stopped.** The
    spec's literal DM-keyword regex gave AmazonHelp a deflection_rate of 0.75% on the first real
    run — implausible on its face given BUILD_SPEC.md §4's own prediction. Sampling 25 real
    first-agent-replies showed Amazon's actual redirect phrasing is link-gated ("please contact
    us here: <url> so we can assist you accordingly"), not the word "DM". Validated the candidate
    patterns against all 108 brands before adding them: they concentrate in AmazonHelp (5.2% hit
    rate) and Uber_Support (1.2%), and barely touch hulu_support (0.7%) or any brand whose links
    point to genuine troubleshooting docs — so the fix targets the real gap, not a cosmetic one.
    After the fix, AmazonHelp's deflection_rate rises to 5.9% (first reply) / 9.1% (any agent turn
    in the thread) — still far under "well north of 50%". Stopped widening the regex there instead
    of chasing that number: the residual ~51% of Amazon's first replies are diagnostic questions
    with no resolution and no off-platform redirect language at all, a third category the spec's
    two-bucket deflection/substantive framing has no slot for. Reporting that gap honestly is a
    better use of the finding than forcing the regex to agree with a prior.
