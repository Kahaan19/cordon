# REPORT.md skeleton (≤ 6 pages)

Placeholders in `{{braces}}` are filled from `RESULTS.md`. Prose in *italics* is pre-written framing
you should keep — it is where the argument lives. Delete every heading you cannot fill with a real
number.

---

## 0. Headline (½ page — this is the page they actually read)

> **{{BRAND}} publicly deflects {{deflection_rate}}% of first replies to DMs. CORDON converts
> {{coverage_at_5}}% of incoming volume into a helpful public reply with a statistically guaranteed
> bad-reply rate of ≤5% (90% confidence, Clopper–Pearson, n={{n_calib}}). The obvious
> single-prompt LLM approach reaches only {{b2_coverage_at_5}}% at the same guarantee.**

**Table 1 — coverage at matched risk** (the only table that matters):

| System | Auto-handled @ ≤1% risk | @ ≤5% | @ ≤10% | Judge quality (auto slice) | $/1k tickets |
|---|---|---|---|---|---|
| B0a Deflector | | | | | |
| B0b Coward | 0% | 0% | 0% | n/a | |
| B1 Nearest-neighbour | | | | | |
| B2 Obvious LLM | | | | | |
| **B3 CORDON** | | | | | |

One sentence on what to do with this: *at a risk budget of X%, this replaces Y human replies per
1,000 tickets, at Z% of the cost.*

---

## 1. Problem framing (¾ page)

- What "good" means for {{BRAND}}, in four checkable properties: **grounded** (no claim not
  supported by evidence), **actionable** (moves the customer forward, not just acknowledges),
  **in-voice** (passes the brand's measurable style profile), **correctly routed**.
- *The framing decision that drove everything: the target is not "reply like the brand did." The
  brand's public reply is a deflection {{deflection_rate}}% of the time. Imitating the corpus means
  learning to say "please DM us," which is precisely the behaviour a support team would pay to
  remove. So the system is optimised for **how much volume it can safely resolve**, and the
  historical reply is treated as weak evidence, not as ground truth.*
- Brand selection: one paragraph + the audit table (`report/brand_audit.md`), showing this was an
  evidence-based choice among {{n_brands}} candidates.
- **What I chose not to build**, with one-line reasons — see `BUILD_SPEC.md` §14. Lead with the
  biggest: *no multi-turn state, because an offline corpus cannot tell me what the customer would
  have said next, and evaluating a dialogue manager against a fixed transcript is theatre.*

---

## 2. System (¾ page, one diagram)

`classify → retrieve+diversify → playbook → draft → verify (linter · claim-check · self-consistency)
→ risk score → conformal threshold → auto | escalate(reason)`

Emphasise the two non-obvious parts:
1. **Playbooks** — procedure mined once from ~100 historical resolutions per intent, so the draft is
   grounded in *how this brand resolves this*, not merely in *what this brand's tweets sound like*.
2. **The threshold is not a hyperparameter.** It is chosen by walking the risk-sorted calibration
   set and stopping where the binomial upper confidence bound on the bad-reply rate crosses the
   budget. Explain in two sentences; show the 6-line function.

---

## 3. Evaluation design (¾ page)

- Golden set: 200 items, 4 strata, sampled from the test window only, labelled by one person;
  intra-annotator κ = {{kappa_intent}} (intent) / {{kappa_escalate}} (escalation).
  *Every accuracy number below should be read against that ceiling — an automated metric cannot be
  more reliable than the labels it is scored on.*
- Judge: {{JUDGE_MODEL}}, 5-dimension rubric. Agreement with human on 80 blind items:
  ρ = {{rho_by_dim}}; ±1 agreement = {{pm1}}; Krippendorff α = {{alpha}}.
- **Judge trap set** — 40 replies with injected known defects. Detection rate by defect:

| Injected defect | Judge detection rate |
|---|---|
| invented policy | |
| unbounded promise | |
| PII request | |
| wrong intent | |
| voice drift | |
| truncation | |

  *Conclusion sentence: I report {{trusted_dims}} with confidence and treat {{untrusted_dims}} as
  indicative only, because my judge demonstrably cannot detect those defects.*
- Bias probes: position flip rate {{flip}}, length-padding score delta {{len_delta}},
  same-family self-preference {{self_pref}}.

---

## 4. Results vs. baselines (¾ page)

Table 2 — intent: macro-F1 with 95% bootstrap CI, on `natural` (or reweighted), per-class table in
the appendix. Table 3 — escalation: precision/recall, unnecessary-escalation rate,
missed-escalation rate. Table 4 — reply quality: judge dims, `unsupported_claim_rate`,
linter-violation rate, **human blind pairwise win-rate vs. the brand's real reply** ({{winrate}}%
on n=60). Table 5 — ablations, one row each.

Call out honestly whichever ablation showed no benefit. *A component that did not earn its place is
a result, and reporting it is cheaper than defending it later.*

---

## 5. Failure analysis (1 page — top 5, each with a real example)

Template per mode: **name · frequency (n/200 + which strata) · a real message with its tweet ID ·
the actual draft produced · hypothesis · would my proposed fix have caught it?**

Likely candidates found by `report/failures.md`; replace with what you actually see:
1. Multi-intent messages collapse to one label, and the draft answers the easier half.
2. Retrieval returns near-duplicate generic threads → drafts regress to the brand's mean deflection.
3. Sarcasm read as praise; anger axis compensates but intent does not.
4. Time-sensitive issues (outages, incidents) answered confidently from a stale 2017 corpus — the
   system has no notion that some knowledge expires.
5. Over-escalation of angry-but-trivial messages: anger is a strong LR coefficient, so rage about a
   simple, answerable question buys a human it doesn't need. Quantify the wasted human time.

---

## 6. What is misleading about my headline number (½–¾ page — MANDATORY, make it the best section)

*Pre-seeded; keep the ones that survive contact with your data, delete the rest, add what you find.*

1. **The guarantee is conditional on the calibration distribution.** Clopper–Pearson bounds the
   error rate on data drawn like the calibration set. Real traffic drifts — a product launch or an
   outage moves the mix overnight and the bound silently stops holding. It is a statement about
   {{n_calib}} tweets from late 2017, not a promise about next Tuesday.
2. **`bad_to_autosend` is my own judgement.** The loss the bound controls is defined by one
   annotator with κ={{kappa_escalate}} against himself. A tighter bound on a shakier label is not
   progress. The confidence interval on the label noise is wider than the interval on the metric.
3. **n=200, so the CIs are wide.** {{example_ci}} — a difference of a few points between systems is
   not a difference. Where two systems' intervals overlap, the report says "indistinguishable," not
   "better."
4. **The judge is the same model family as the generator.** Measured self-preference is
   {{self_pref}}; I correct for it with human labels on 80 items, but the correction has its own
   interval and the residual bias favours my system.
5. **Similarity to the historical reply is a fraudulent metric here, and I can prove it.** B0a, a
   constant string, achieves {{b0a_rougeL}} ROUGE-L against the brand's real replies —
   {{b0a_vs_b3}} of what CORDON achieves. Anyone reporting overlap-with-ground-truth on this dataset
   is largely reporting deflection-rate. *(Include this exhibit even though — because — it makes a
   metric other submissions will headline look bad.)*
6. **Coverage is inflated by easy classes.** {{easy_share}}% of the auto-handled slice is
   praise/thanks and simple FAQ. Excluding those, coverage on *genuinely problematic* messages is
   {{coverage_hard}}%, which is the number a support lead should actually plan against.
7. **Offline ≠ online.** No customer ever saw these drafts. Every quality number is a proxy for
   satisfaction, and the corpus contains no satisfaction signal beyond a noisy "thanks."
8. **Survivorship.** Only public threads exist here. Everything that moved to DM — i.e. every hard
   case the brand actually solved — is invisible. The corpus systematically under-represents exactly
   the population escalation is meant to catch.
9. **The re-labelling κ is intra-annotator.** It measures whether I am consistent, not whether I am
   right. Two annotators would likely agree less.
10. **{{leak_delta}} of apparent performance was leakage.** Under a random split, macro-F1 is
    {{f1_random}}; under the time split, {{f1_time}}. I report the lower number; many pipelines
    default to the higher one.

---

## 7. With one more week (¼ page — concrete and ordered, not a wishlist)

1. A second annotator on 150 items → real inter-annotator agreement, and a re-derived risk bound on
   adjudicated labels. (Biggest credibility gain per hour, by a distance.)
2. An open-weights cross-family judge and a 3-judge ensemble with reported disagreement, retiring
   the self-preference caveat.
3. Drift monitoring: track the calibration-set feature distribution and re-certify the threshold on
   a rolling window; alert when the bound is no longer defensible.
4. Two more brands to test whether the playbook + calibration approach transfers or whether it was
   fitted to one brand's habits.
5. A small human-in-the-loop trial: route the auto-slice to an agent as a *draft*, measure
   edit-distance-to-sent — the only cheap proxy for real acceptance available without shipping.

---

## Appendix
Per-class F1 table · confusion matrix · full ablation grid · prompts (verbatim) · annotation guide ·
decision log · `report/traces.html` walkthrough (say explicitly: *open this file to see every
decision the system made on every golden item*).
