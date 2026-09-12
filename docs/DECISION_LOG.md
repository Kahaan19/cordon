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

28. **Measured `gemini-3.5-flash-lite`'s free-tier RPM directly: 15 requests/minute** (from the
    live `GenerateRequestsPerMinutePerProject...FreeTier` quota violation, not a guess). RPD
    could not be pinned down the same way: Google's rate-limits docs no longer publish a
    per-model table (confirmed via WebFetch — only "view your limits in AI Studio," which is
    authenticated and unreachable from here), and deliberately did not burn quota hunting for the
    exact RPD ceiling once ~70 real calls succeeded today with zero RPD-type violation (only RPM
    ones) — that's a fine lower bound for planning; finding the exact number would cost more
    quota than the answer is worth. TPM was never the bottleneck in any test — our prompts are a
    few hundred tokens, nowhere near a per-minute token cap. Also split `GeminiBackend`'s retry
    condition: a `PerDay`-scoped 429 fails immediately (rule 10, fail loudly) instead of burning
    all 10 retries against a 60s-capped backoff that can't possibly outlast a ~24h quota window;
    `PerMinute`/transient errors still get the full retry treatment.

29. **Trimmed the Phase 5 ablation grid to `-retrieval`, `-linter`, `-self_consistency`,
    `-conformal` — dropped only `-playbook`.** Estimated remaining Gemini call volume against
    the confirmed RPM=15 finding (#28) before starting Phase 3:

    | Phase | Source | Calls |
    |---|---|---|
    | 3 | playbook mining, 1/intent (10, skip `other`) | 10 |
    | 4 | agent × 200 golden items: classify(1) + draft self-consistency(3) | 800 |
    | 5 | B2 baseline, 1/item | 200 |
    | 5 | `-retrieval`, `-playbook` ablations (only these two change the draft prompt; `-linter`/`-self_consistency`/`-conformal` are post-hoc or reuse-of-fewer-cached-samples, 0 extra calls) — 2 × 200 × 3 | 1,200 |
    | 6 | judge scoring is 100% Ollama (0); trap-set defect injection, ~40 items | ~30 |
    | **Total** | | **~2,240** |

    RPD for `gemini-3.5-flash-lite` is unconfirmed (#28's lower bound only: >~70). Rather than
    gamble the whole remaining build on an unknown ceiling, cut the one ablation that's purely
    a cost center with no free-tier benefit: `-playbook` costs another 600 calls and duplicates
    what `-retrieval` already demonstrates (the value of grounding evidence in the draft
    prompt). `-linter`, `-self_consistency`, and `-conformal` stay in the grid — they cost zero
    additional calls (linter/conformal are downstream of generation; the self-consistency
    ablation just uses fewer of the same cached samples), so cutting them would only make the
    evaluation worse for no budget benefit. New total: **~1,640 calls (~1.8h of issuing time at
    RPM=15)**, comfortably inside a single day under any plausible RPD. Fallback if a day
    boundary is still hit mid-run: stop and resume tomorrow from the committed cache — free and
    lossless, which is what the cache exists for (#14, #28's `PerDay` fail-fast fix).

    **Considered and rejected: shrinking the golden set instead.** BUILD_SPEC.md §12 explicitly
    protects it ("Never cut: the golden set...") — it's the single highest-value deliverable in
    the whole build, and every downstream metric (calibration, judge validation, baselines)
    reads off it. A rate-limit inconvenience is not a reason to weaken the one thing every other
    number in the report depends on; the ablation grid is the correct place to absorb this cut
    because BUILD_SPEC.md §12 itself pre-approves trimming it (cut-order item 5), and because
    unlike the golden set, removing one ablation doesn't touch any headline number — it just
    removes one supporting comparison row.

30. **Intent assignment over the pool corpus reuses the taxonomy's own centroids (nearest-
    centroid, zero new LLM calls) instead of a fresh classifier.** Pool threads were never
    individually intent-labelled — only the 4,000-message taxonomy sample was. Recomputing
    `taxonomy.induce()` (deterministic, cached) and averaging each final intent's member-cluster
    vectors gives a centroid per intent; assigning every pool thread to its nearest centroid
    labels the full corpus for playbook mining without spending Phase 4's classifier budget
    early. This is an embedding heuristic, not the real classifier — expect Phase 4's LLM
    classifier to disagree with it on some fraction of borderline threads, same seam as the
    taxonomy's own ARI-confirmed boundary (#24).

31. **Retrieval diversity: MMR helps per-query but the corpus is genuinely redundant.**
    Inspecting one query directly (a Sunday Night Football outage) showed MMR correctly
    skipping a near-duplicate complaint in favor of a differently-angled one — it works. But
    the aggregate mean pairwise cosine similarity only drops from 0.790 (raw top-8) to 0.764
    (MMR top-3, λ=0.5) across 50 sampled queries. Real customers describing the same live
    incident (an outage, a blackout) genuinely sound alike; MMR can't invent diversity that
    isn't in the underlying corpus. Reported as-is rather than tuning λ to produce a more
    dramatic-looking number — the honest finding is that this corpus's redundancy is a property
    of live-support data, not a retrieval bug.

32. **Found and fixed a real regex bug in the voice profile, not a genuine 0%.**
    `uses_customer_name_rate` came back 0.0/300 on the first run. Manual inspection of the
    actual sample ("Hey Christy!", "Hi Noah!") showed the greeting pattern was obviously
    present — `GREETING_NAME_RE` was just missing `re.IGNORECASE`, so it only matched an exact-
    lowercase "hi"/"hey". Fixed; re-ran (free, all `gemini-3.5-flash-lite` calls cache-hit) and
    it now reads 12.7%. By contrast, `signoff_rate = 0.0` is real: directly re-checked for any
    `^XX`-style pattern (case-insensitive) across the same 300 replies and found zero — Hulu's
    agents genuinely don't sign off with initials, unlike AmazonHelp's `^KP` style seen in
    Phase 1. Worth stating plainly: a metric reading exactly 0% is a prompt to verify by hand,
    not to report — one was a bug, the other was real, and they looked identical before checking.

33. **Hand-authored 13 of the 15 redteam items; only 2 were minable from real 2017 data.** After
    fixing two regex false positives (`self_harm` matched "trying to **end it** [before the free
    trial ends]"; `spam` matched "**follow me**" inside a legitimate DM-policy complaint), the
    honest yield from mining the 2,219-thread test window was 2 items, both genuine abuse
    ("scam", "moron"). Checked the *whole* 10,353-thread pool, not just the test window, before
    concluding this is a real corpus fact rather than a mining bug: zero emails, one phone-number
    fragment, in the entire brand. Prompt injection can't exist in 2017 discourse at all.
    BUILD_SPEC.md §9.1 explicitly allows "hand-written or mined" for this stratum for exactly
    this reason. Hand-authored 3 self-harm, 4 prompt-injection, 4 PII, 2 spam items, each with a
    placeholder ID (`synthetic_redteam_NN`) and `synthetic: true` in `sampled_items.jsonl` — never
    a fake real-looking tweet ID — so provenance stays unambiguous when this data is read back
    later. `report/sampling_stats.md` states the real/synthetic split plainly rather than
    burying it in an unlabelled total of 15.

34. **Disabled qwen3's thinking mode (`think=False`) for every judge call.** First live Ollama
    call through `llm.py` (a trivial "say hi in three words") took 56 seconds and returned
    empty `content` — qwen3 is a hybrid-thinking model that puts its chain-of-thought in a
    separate `message.thinking` field by default and had spent the entire 1024-token budget
    thinking without ever reaching an answer. `think=False` (an `ollama` chat-API parameter)
    drops the same call to 0.5s with `content` correctly populated, and schema-forced JSON
    (the `supported/unsupported/irrelevant` verdict shape) now works cleanly. Every judge call
    in this project is a short, structured verdict or rubric score — exactly the case thinking
    mode doesn't help and actively breaks. Caught before Phase 4's real agent run, not after.

35. **Phase 4's `risk_score` is a real feature vector with a hand-set placeholder weighting,
    not the fitted model BUILD_SPEC.md §7.4 describes.** `golden_v1.jsonl` is still being
    hand-labelled — there's no `calib`-split `should_escalate` ground truth to fit a logistic
    regression against yet. Built all 7 features for real (margin, retrieval similarity,
    self-consistency, `needs_account_access`, linter violations, unsupported-claim rate,
    anger/severity), assembled into `RiskScore` with `weights_source: "placeholder"` so nothing
    downstream can mistake this for a calibrated number. `RISK_PLACEHOLDER_WEIGHTS` and
    `RISK_DECISION_THRESHOLD_PLACEHOLDER` in `config.py` are hand-set, not fit, and are Phase
    6b's job once labelling finishes — that phase replaces the weights and threshold, not the
    feature computation, which is already real.

36. **Self-consistency's 3 T=0.7 draft samples get distinct cache keys via a prompt suffix, not
    a change to `llm.py`'s cache-key formula.** `complete()`'s cache key is `(model, system,
    prompt, temperature, max_tokens, schema)` — three identical calls at the same temperature
    would all hit the same cache entry, silently collapsing "3 samples" into 1 repeated 3x and
    making the self-consistency signal meaningless. Appending an inert HTML-comment-style
    marker (`<!-- sample1 -->`) to 2 of the 3 prompts changes their cache key without touching
    the question being asked, and — critically — doesn't change the cache-key computation
    itself, so every previously cached call from Phases 2-3 stays valid. Widening the cache key
    schema instead would have invalidated all of them.

37. **Split Phase 4 across three files: `linter.py` (deterministic checks), `verify.py`
    (claim-check/self-consistency/risk-score/hard-overrides), `agent.py` (classify/draft/
    retrieve/orchestration).** Same reasoning as the taxonomy.py/taxonomy_finalize.py split
    (#26): the combined pipeline passed ~250 lines, and the split tracks real seams — the
    linter is pure, zero-dependency Python that BUILD_SPEC.md §13 tests in isolation (tests
    6-9); verify.py's functions are the probabilistic/LLM-touching verification layer; agent.py
    is just the pipeline that calls all of them in order.

38. **The linter's `missing_signoff` rule only fires when the brand's own voice profile shows
    signoffs are actually used (`signoff_rate > 0.3`).** BUILD_SPEC.md §7.3(a) states "sign-off
    present" as an unconditional rule, but hulu_support's measured `signoff_rate` is 0.0 (#32) —
    enforcing it unconditionally would flag every single draft this agent ever produces for a
    brand that structurally doesn't sign off with agent initials. The rule is real and will
    fire correctly for a brand whose voice profile shows real signoff usage; it's parametrized
    by the brand's own measured voice rather than hard-coded to the spec's illustrative example.

39. **Added a 60-second request timeout to both `llm.py` backends.** The first full 10-message
    agent run hung for over an hour with ~4 seconds of actual CPU time — a stalled connection
    (most likely the machine sleeping mid-request) left the process waiting forever with no
    error, no retry, no progress, because neither `genai.Client` nor `ollama.Client` had an
    explicit timeout configured. `types.HttpOptions(timeout=60_000)` (milliseconds) for Gemini,
    `timeout=60` (seconds) for Ollama via its underlying httpx client. A stalled connection now
    fails loudly within a bounded time instead of hanging indefinitely (rule 10) — Gemini's
    existing retry loop still applies on top of that for genuinely transient errors.

40. **Claim extraction drops questions.** Inspecting the first real 10-message agent run found
    the judge scoring identical question phrasing inconsistently across calls — "Which device
    do you use?" came back `supported` in one trace, `unsupported` in another for the same
    words. A question has no truth value for evidence to support or contradict; naive
    sentence-splitting was feeding them to the judge anyway. Filtered questions (sentences
    ending `?`) out of `extract_claims()`. Left commitment phrases in — "we'll share your
    feedback," "we'll definitely share your interest" — which scored `unsupported`
    consistently and correctly (nothing in the retrieved evidence promises that); this is the
    claim-check catching vague promise-making the linter's narrower regex-based
    `unbounded_promise` rule doesn't reach, not noise, and a good sign the two checks are
    complementary rather than redundant.

41. **Added `unsupported_claim_rate >= 0.8` to the hard-override list (BUILD_SPEC.md §7.4).**
    A real trace (`app_bugs_and_ui_complaints`, draft "Oh no! We'll share your feedback! What
    device are you streaming from?") had `unsupported_claim_rate=1.00` — the worst grounding
    failure the pipeline can detect — but scored `risk_score=0.23` under the placeholder
    weights (`unsupported_claims`' 0.15 weight caps its own contribution at 0.15, so it can't
    cross the 0.5 threshold alone) and would have auto-sent. Same asymmetric-cost logic as the
    other hard overrides: a near-fully-hallucinated draft must never auto-send regardless of
    what the rest of the score says, learned or not. Implemented as `check_claim_override()` in
    `verify.py`, checked separately from `check_hard_overrides()` because it depends on
    `claim_check()`'s output and can only be evaluated after drafting, not on the raw message
    before drafting starts like the other four overrides. `RISK_PLACEHOLDER_WEIGHTS` (0.15 etc.)
    are left untouched on purpose — Phase 5's `calibrate.py` fits real logistic-regression
    coefficients on the calib split and replaces them; hand-tuning a number that's about to be
    refit is wasted effort. The override threshold (0.8) is not part of that fit — it's a hard
    rule on either side of the placeholder-vs-fitted line, same as the message-based overrides.

42. **Added a `fabricated_url` linter rule after B2 invented a plausible-looking support URL.**
    Running the real B2 baseline (Phase 5) on a "Hulu on the Wii" complaint produced: "checking
    out our currently supported devices here: http://hulu.com/support/articles/200730109" — a
    literal URL, not the `<url>` placeholder token the existing `url_not_in_evidence` check
    looks for, so it slipped through uncaught. But `ingest.py`'s `clean_text()` always masks
    real URLs to `<url>` — every evidence source (retrieved replies, playbooks) is built from
    that cleaned corpus and can therefore never contain a literal URL. That makes any literal
    `http(s)://` in a draft fabricated by construction, unconditionally — no evidence
    comparison needed, unlike `url_not_in_evidence`. Added as its own violation code so the two
    stay distinguishable in reporting. Applies to every system through the shared `lint_draft()`
    call, CORDON included, not just B2.

43. **baselines.py: B0a/B0b (majority intent + most common real deflection reply), B1 (TF-IDF +
    logistic regression, nearest-neighbour reply, escalate-below-median-similarity), B2 (one
    fair generator call) — all through the identical `Trace` schema as `agent.py`.** B1's median
    similarity threshold (0.454) is fit on the calib split via cosine similarity alone — no
    human labels needed, so nothing here waits on `golden_v1.jsonl`. Ran all four on the same
    10 demo messages as Phase 4's agent run: B2's failures are exactly the honest, expected
    ones — inventing a specific, unevidenced policy ("episodes typically become available the
    day after they air") and the fabricated URL above — while B0a/B0b's constant deflection
    reply is real, mined from the pool (`"Can you DM us more info?..."`), not synthesized.

44. **Picked "clarity" as the judge rubric's 5th dimension.** BUILD_SPEC.md §0's thesis names
    four qualities — groundedness, actionability, safety, voice — for a "5-dimension rubric"
    without naming the 5th anywhere. `clarity` is the natural complement, and §9.4.2's own
    trap-set defect list includes "truncated mid-sentence," which isn't a groundedness/
    actionability/safety/voice problem — it needs a dimension to land on, and it does
    (`truncated_mid_sentence` detection: 90%, the trap set's strongest result).

45. **Judge trap set (n=40, real substantive replies from the retrieval index, deterministic
    defect injection) — full per-defect detection rates:**

    | defect | dimension checked | detection rate |
    |---|---|---|
    | truncated_mid_sentence | clarity | 90% |
    | pii_request | safety | 80% |
    | subtly_wrong_product_name | groundedness | 72% |
    | invented_policy | groundedness | 70% |
    | wrong_intent | actionability | 52% |
    | unbounded_promise | groundedness | 42% |
    | wrong_signoff_voice | voice | 42% |

    Trust `clarity` and `safety` scores; treat `voice` and the groundedness-via-
    `unbounded_promise` signal specifically as closer to decorative — the judge catches an
    *invented policy* 70% of the time but a vague *promise* only 42%, even though both are
    grounding failures by the same rubric dimension. "Detected" means the mapped dimension
    scored strictly lower on the defective copy than the original — this tests the actual
    production rubric, not a separate classifier nobody else uses.

46. **Position-bias probe: 67% flip rate.** Swapping which side (A/B) the same two replies
    appear on changed the pairwise winner two-thirds of the time on a 15-item sample. This is a
    real, serious finding, not swept under the rug: `compare_pair()`'s pairwise mode is not
    reliable enough on its own to trust for anything — a report using pairwise judge verdicts
    (e.g. the §9.3 blind pairwise win-rate framing) must randomize and average over both
    orderings per item, never read a single-order verdict as ground truth. The 5-dimension
    rubric (`score_reply`) doesn't have this specific failure mode since it scores one reply
    at a time with no ordering to be biased by.

47. **Length-bias probe: harmless filler inflated every score except safety.** Padding a real
    reply with a content-free pleasantry (docs/DECISION_LOG.md config `LENGTH_PROBE_FILLER`)
    moved scores by +0.87 (groundedness), +0.87 (actionability), +0.73 (voice), +0.80
    (clarity), +0.00 (safety) on a 1-5 scale, averaged over 15 items — a large, systematic
    "longer sounds better" bias affecting every dimension that isn't a hard safety check.
    Any headline number built from absolute rubric scores should note this: two replies that
    differ only in padding will not score equally, and the judge cannot be trusted to normalize
    for length on its own.

48. **Self-preference probe: no inflation — if anything, the opposite.** The judge (qwen3),
    blind-scoring its own drafts vs. the brand's real historical replies vs. B1's copied
    replies (15-item sample): qwen_draft=3.80, real_reply=4.03, b1_copied=4.03. The judge rated
    its own generated text *lower* than authentic replies, not higher — no same-family
    self-preference bias observed in this cross-family setup (qwen3 judge, Gemini generator;
    this probe additionally has qwen3 act as a one-off drafter purely to test the judge against
    its own model family, per BUILD_SPEC.md §9.4.3c). Worth stating plainly since it's the
    reassuring result: this specific bias, which the project's cross-family design (§2) exists
    to guard against, doesn't show up here.

49. **Added a minimal, opt-in call log to llm.py for ops metrics (§9.3: cache hit-rate,
    tokens/ticket).** `Trace` only carries `cost_usd`/`latency_ms`; per-call token counts and
    cache-hit status were being discarded after every `complete()` call. Threading a log
    parameter through every classify/draft/claim_check call site in agent.py and verify.py
    would touch a lot of already-tested code for a reporting concern. Instead: a module-level
    accumulator in llm.py (`reset_call_log()`/`get_call_log()`), appended to inside `complete()`
    itself regardless of caller. `evaluate.py` calls `reset_call_log()` before processing one
    golden item and reads back exactly the calls that item made -- zero changes needed to any
    other module.

50. **Split llm.py into llm.py (cache + complete() + call log) and llm_backends.py (Gemini +
    Ollama backend classes) once the combined file passed ~250 lines.** Same reasoning as the
    taxonomy.py/taxonomy_finalize.py and agent.py/verify.py/linter.py splits: caching/dispatch
    is one job, backend-specific API integration is another. `JUDGE_MODEL`/`GEN_MODEL` stay
    re-exported from `cordon.llm` (not moved) since judge.py, judge_validation.py, verify.py,
    baselines.py, taxonomy.py, taxonomy_finalize.py, playbook.py, and agent.py all already
    import them from there -- the split changes internal structure, not the public interface
    other modules depend on.

51. **Resolved BUILD_SPEC.md §8's "calib/test" wording against docs/ANNOTATION_GUIDE.md §1's
    "test window only" for the golden set.** §8 says "fit on the calib split of the golden set,
    evaluate on test" -- but the entire 200-item golden set is drawn from the test window only
    (§1), so there's no golden-set overlap with the original pool/calib/test thread split to
    read those words against literally. Resolved as: split the 200 golden items themselves,
    stratified by `stratum`, into two roles -- `golden_fit` (risk-model fitting + threshold
    search) and `golden_holdout` (the honest held-out evaluation §8 is actually asking for).
    `GOLDEN_FIT_FRACTION = 0.5` in config.py. This is a disambiguation of genuinely ambiguous
    spec wording, not a disagreement with it -- the underlying intent (fit and evaluate on
    different data) is preserved exactly.

52. **calibrate.py fails loudly, specifically, on a missing `bad_to_autosend` label rather than
    approximating it from `should_escalate`.** BUILD_SPEC.md §7.4's risk-model fit and §8's
    threshold search use two different human labels: `should_escalate` (collected during the
    main labelling pass, available as soon as golden_v1.jsonl is labelled) and
    `bad_to_autosend` (BUILD_SPEC.md §3's separate, later, per-system, blind-to-system pass,
    collected only after every system has run on the golden set -- not yet collected, and not
    something this project's own annotation guide treats as optional). `main()` fits the risk
    model and reports real coefficients first (it only needs `should_escalate`), then fails
    with a specific, actionable error naming exactly which file is missing and why it can't be
    substituted -- rather than silently proceeding with a proxy for the one label whose entire
    purpose is to catch what the automated signals miss.

53. **Verified calibrate.py's risk-model-fitting path end-to-end against a small synthetic
    golden set (16 real messages, fake should_escalate labels, scratchpad only, never
    committed) before trusting it.** Confirms the mechanism -- running the real agent on each
    item, extracting the 7 risk features, fitting LogisticRegression, reporting coefficients --
    works correctly today. No real RESULTS.md is produced by this or any run until
    golden_v1.jsonl and bad_to_autosend_v1.jsonl exist for real; CLAUDE.md rule 1 forbids
    hand-written numbers, and fabricated labels would make any headline number produced today
    worse than useless -- it would look real.

54. **Found and fixed a real bug in baselines.py while wiring up evaluate.py's ops metrics:
    every baseline's `latency_ms` was hardcoded to `0.0`, never measured.** B0a/B0b/B1/B2 all
    make at least one real call (claim_check's judge call, B2's generator call), so reporting
    zero latency for them was flatly wrong, not just imprecise -- it would have made every
    baseline look instantaneous next to CORDON's real, measured latency in the ops table. Fixed
    by capturing `time.perf_counter()` at each baseline function's own entry and threading it
    into `_make_trace()`, the same pattern `agent.py`'s `run_agent()` already uses. Caught by
    building the metric that actually reads the number, not by inspecting the field in
    isolation -- a reminder that a field nobody consumes yet can hide a real bug indefinitely.

55. **evaluate.py runs the CORDON system's traces once, not twice.** First draft computed
    `evaluate_system("cordon", ...)`'s metrics, then separately re-ran every holdout item
    through `run_system_on_item("cordon", ...)` again just to get traces for the coverage-risk
    curve -- doubling CORDON's real Gemini/Ollama call volume on every evaluation run for no
    reason. Fixed by having `evaluate_system()` return `(metrics, traces)` so the caller reuses
    what was already computed.

56. **metrics.py: bootstrap CIs resample (y_true, y_pred) together, paired, never
    independently.** An earlier internal draft considered resampling each array on its own,
    which would compute a CI for a statistic that no longer corresponds to any real labelling
    of any real item -- independently shuffling true and predicted labels destroys the very
    correspondence the metric is supposed to measure. `bootstrap_ci_paired()` draws one set of
    row indices and applies it to every array, preserving per-item pairing across every
    resample. BUILD_SPEC.md §9.3's 2000-resample, every-headline-number-has-a-CI requirement is
    implemented generically here, once, reused by intent macro-F1 and escalation F1 both.

57. **Verified evaluate.py end-to-end against the same 16-item synthetic golden set as
    calibrate.py (real messages, fake labels, scratchpad only) before trusting it.** All 5
    systems ran, `RESULTS.md`-shaped output was produced with a real git SHA + timestamp +
    config hash header, and the missing-`bad_to_autosend` section degraded gracefully
    (`coverage_curve: null` with a logged reason) instead of crashing the whole report. Intent
    macro-F1 reads 0.000 for every system in this synthetic run -- expected and correct: the
    fake labels are a constant `"other"` that none of the five real classifiers happen to
    predict for these particular real messages, not a metric bug. No real RESULTS.md is
    committed from this or any run until golden_v1.jsonl exists for real.

58. **report.py: split into report.py (orchestration) + report_traces_html.py +
    report_index_html.py, no templating library.** Every other report-writer in this project
    (sampler.py, index.py, judge_validation.py) builds its markdown output as plain Python
    strings, no jinja2, despite it being an allowed dependency (CLAUDE.md rule 6) -- kept HTML
    generation consistent with that precedent rather than introducing templating for this one
    module. The three-way split matches the taxonomy/agent/llm splits: rendering traces.html
    and index.html are two genuinely separate jobs sharing only a CSS constant.

59. **report/index.html's charts are hand-rolled inline SVG, not a charting library.**
    BUILD_SPEC.md §10 says "no CDN," and a bundled JS charting library would need either a CDN
    or a local copy to manage -- a `_svg_line_chart()` helper (~20 lines: linear-scale two
    Python closures, a `<polyline>`, some `<circle>`s) covers the coverage-risk curve with zero
    dependencies and stays inside the "no build step" spirit.

60. **traces.html/index.html sections needing data not yet collected render an explicit "not
    yet available" state with the exact missing dependency named, mirroring evaluate.py's
    graceful degradation -- never a fabricated placeholder number.** Coverage-risk curve and
    cost-sensitivity both need `bad_to_autosend` (docs/ANNOTATION_GUIDE.md §3, not yet
    collected); judge agreement needs 80 human-scored items (BUILD_SPEC.md §9.4.1, also not yet
    collected, and no tooling exists yet to collect it -- out of this phase's scope). Verified
    end-to-end against the same 16-item synthetic golden fixture used for calibrate.py/
    evaluate.py (scratchpad only, never committed): both pages rendered correctly, HTML
    escaping held up on real punctuation-heavy tweet text, and a real hard-override case
    (`unsupported_claim_rate >= 0.8`) is visible in a card's decision reason -- confirming
    Phase 4's override logic surfaces correctly in the trace viewer. report.py itself still
    fails loudly (refuses to render anything) if golden_v1.jsonl is missing entirely, same as
    calibrate.py/evaluate.py -- the distinction is between a foundational input (fail) and an
    optional section's dependency (degrade that section only).
