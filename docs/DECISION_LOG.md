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

22. **Swapped `google-generativeai` for `google-genai` in `llm.py` (CLAUDE.md rule 6 dependency
    change).** The first live taxonomy run (Phase 2) hit a 401 after ~18 minutes of 429 backoff.
    `google-generativeai` itself prints "all support has ended... switch to google.genai" on
    import — it's officially dead, not a transient bug. Verified the failure was structural, not
    the SDK: an isolated fresh call with the new SDK, both via `api_key=` and via an explicit
    OAuth2 Bearer `Credentials` object, hit the identical 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED` from
    `generativelanguage.googleapis.com` — three different auth mechanisms, one consistent error,
    which is the key itself, not a transport mismatch (a fresh `AIza...` key from
    aistudio.google.com/apikey resolves this; see SETUP.md §3). Migrated `GeminiBackend.generate()`
    to `genai.Client(api_key=...).models.generate_content(...)` regardless, since the old SDK is
    provably unmaintained and would fail again on the next call even with a valid key.

24. **My taxonomy is stable at mean ARI 0.565 (range 0.47-0.68) across 3 seeds and k in
    {24, 36}.** The least stable rerun (seed 1, k=24) puts the single most-confused pair at
    `playback_streaming_failure` vs. `app_bugs_and_ui_complaints` (197 of 4,000 messages) — and
    that is the exact same seam I flagged by hand while merging clusters 16 and 23 (both
    generic "app is broken" clusters that could plausibly sit on either side). The automated
    check and the human merge call landed on the same boundary independently; that's the
    taxonomy's real seam, not a labelling accident, and `taxonomy/intents.yaml`'s exclude field
    for both intents says so explicitly.

25. **Committed the human merge decision (`taxonomy/merge_map.yaml`, `taxonomy/boundary_notes.yaml`)
    as real inputs, not just a one-off argument.** `taxonomy_finalize.py` reads them back to
    regenerate `taxonomy/intents.yaml` byte-for-byte (verified via `make taxonomy-finalize`), so
    the one genuinely human step in Phase 2 is still fully reproducible from committed files, not
    a step a reviewer has to trust happened once and can't rerun.

26. **Split `taxonomy.py` into `taxonomy.py` (induce) and `taxonomy_finalize.py` (merge +
    consolidate + stability) once the combined file passed ~250 lines** (CLAUDE.md rule 9).
    They're genuinely two different jobs on two different schedules — induction is a
    deterministic machine step; finalization depends on a human merge decision — so the split
    tracks a real seam in the workflow, not an arbitrary line-count dodge.

27. **Added an LLM consolidation pass for intents merged from 2+ clusters.** The first draft of
    `taxonomy/intents.yaml` built each merged intent's definition/include/exclude by
    concatenating every member cluster's own LLM output with "; " — honest (never hand-typed)
    but unreadable for the two largest merges (6 and 8 clusters). One extra Gemini call per
    multi-cluster intent (7 calls, `gemini-3.5-flash-lite`, ~$0) synthesizes those into one clean
    sentence each, still built only from what the per-cluster outputs already said.

23. **Repointed `GEN_MODEL` from `gemini-flash-latest` to `gemini-3.5-flash-lite`.** With a
    working key, the taxonomy induce run still failed: `gemini-flash-latest` resolves today to
    `gemini-3.8-flash`, and its free tier is a hard 20-requests-**per day** cap (the exact quota
    named in a live 429 `RESOURCE_EXHAUSTED` response) — a daily ceiling, not the per-minute
    limit BUILD_SPEC.md §2 anticipated, and retrying against it just burns more of the same 20
    requests. Checked alternatives live rather than guessing: `gemini-2.5-flash` and
    `gemini-2.5-flash-lite` both 404 ("no longer available to new users"); `gemini-3.6-flash`,
    `gemini-3.5-flash-lite`, and `gemini-3.1-flash-lite` all responded successfully. Picked
    `gemini-3.5-flash-lite` — a lighter tier than the newest flagship preview, so plausibly a more
    generous free daily quota, while staying in the "Flash" family the spec calls for. Also
    broadened `GeminiBackend`'s retry markers to `429/503/UNAVAILABLE/RESOURCE_EXHAUSTED` (was
    429-only) after hitting a transient 503 mid-run, and raised `MAX_RETRIES` to 10.
