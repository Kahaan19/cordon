# Interview defence sheet

The brief says: *"We will ask you to explain and modify your own code live."* That sentence is the
real grading criterion. **If a technique is in the repo and not on this page in your own words, cut
the technique.** A submission you can defend end-to-end beats a fancier one you can't.

---

## Part 1 — every non-obvious technique in two sentences

**Clopper–Pearson upper bound.** If I saw 2 bad replies in 100 auto-handled messages, the true bad
rate isn't exactly 2% — it's uncertain. Clopper–Pearson gives the largest true rate that would still
plausibly produce 2/100, and I use that pessimistic number so my guarantee doesn't depend on getting
lucky on a small sample.

**Why a "guaranteed" threshold at all.** A 0.5 cutoff is a number someone liked. Instead I sort every
calibration message by risk score, walk the cutoff outward while recomputing the upper bound on the
bad-reply rate, and stop at the last point where the bound is still inside my budget. The output is
"how much can I automate," which is the decision a support manager actually makes.

**Split conformal, in one line.** Fit anything you like on training data; then use a *held-out*
calibration set purely to convert its score into a threshold with a distribution-free guarantee. The
guarantee holds because the calibration and test points are exchangeable — which is also exactly the
assumption that breaks under drift, and I say so in the report.

**Self-consistency as uncertainty.** I sample three drafts at temperature 0.7 and measure how
similar they are to each other. If the model produces three different answers to the same message,
it doesn't have one answer — that disagreement predicts errors better than asking the model how
confident it is, because models are poorly calibrated when they self-report.

**Prediction-powered inference (if you keep it).** The LLM judge is a fast but biased ruler. I have
80 human labels, so I can measure the average bias and subtract it from the judge's estimate over all
200 items. I get the judge's sample size with the human's unbiasedness, and a valid confidence
interval on top.

**Krippendorff's α vs. Cohen's κ.** Both correct agreement for chance; κ is for two annotators on
categories, α handles any number of annotators, missing data, and ordinal scales — which is why the
1–5 judge dimensions use α and the intent labels use κ.

**Adjusted Rand Index (taxonomy stability).** It measures how much two clusterings of the same items
agree, corrected for the agreement you'd get at random. I use it to show my intent taxonomy isn't an
artifact of one random seed.

**MMR diversification.** Greedy re-ranking that trades relevance against redundancy, so the three
retrieved examples aren't three copies of the same thread. λ balances the two; I use 0.5.

**Why time-based splits.** The corpus contains many near-identical tweets about the same incident
minutes apart. A random split puts one in train and its twin in test, so the model looks great by
memorising. I measured the inflation: [X] points of macro-F1.

**Inverse-probability reweighting of the golden set.** I over-sampled hard cases so the metrics
wouldn't be noise, which means the raw set isn't a sample of real traffic. Weighting each stratum by
one over its sampling probability recovers an estimate for the real distribution.

**Bootstrap CI.** Resample the 200 golden items with replacement 2,000 times, recompute the metric
each time, take the 2.5th and 97.5th percentiles. It's how I get an interval without assuming the
metric is normally distributed.

---

## Part 2 — questions they will ask, and the honest answer

**"Why this brand?"** → The audit table. Volume was the wrong criterion; I ranked on how often the
brand actually resolves things in public, because you cannot ground a reply in a corpus of "please
DM us." Show `report/brand_audit.md`.

**"Your intents look arbitrary. Why nine?"** → They came from clustering, but the *count* is set by
the evaluation budget: with 200 golden items, more than ~10 classes means fewer than 20 examples
each and per-class F1 stops being meaningful. And I measured stability across seeds — ARI [X].

**"How do you know your judge is any good?"** → Three ways, and one of them says it isn't: agreement
with a human on 80 blind items; a trap set with injected defects where I measure detection rate per
defect type; and bias probes for position, length, and self-preference. The trap set says my judge
is nearly blind to voice drift, so I don't report voice as a headline.

**"Isn't your golden set just your own opinion?"** → Yes, and that's the binding constraint on
everything downstream. I quantified it: κ = [X] with myself after 24 hours. No metric in the report
can be trusted past that ceiling, which is why the first thing on my one-more-week list is a second
annotator.

**"What if we ran this on live traffic tomorrow?"** → The risk guarantee holds only while traffic
looks like the calibration set. I'd ship it in draft-mode behind an agent first, monitor the feature
distribution for drift, re-certify the threshold weekly, and treat any coverage number as valid only
until the mix moves.

**"Why not fine-tune?"** → With a few thousand threads for one brand and no reliable label for reply
quality, fine-tuning would optimise toward reproducing deflections. The bottleneck here is the
target, not the model.

**"Show me where this fails."** → Open `report/traces.html`, filter to incorrect, and walk them
through failure mode #2 live. Have one specific tweet ID memorised.

**"Change X right now."** → Practise three modifications before the interview:
add an intent to `taxonomy/intents.yaml` and re-run; change the risk budget α from 5% to 2% and
re-derive coverage; add a linter rule and show a draft it newly rejects. Each should be one file and
one make target. **Time yourself.**

**"What would you cut from this if you had half the time?"** → The playbook mining and the ablation
grid. The golden set, the trap set and the calibrated threshold are load-bearing; everything else is
improvement.

**"What's the weakest part?"** → The `bad_to_autosend` label. The whole guarantee is a tight bound
on a noisy definition written by one person. That's an honest answer and it lands better than a
defensive one.

---

## Part 3 — before you submit

- [ ] Fresh clone → `make reproduce` → under 15 minutes, no API key, numbers match `RESULTS.md`.
- [ ] Every file in `src/` re-read once. Delete anything you can't explain.
- [ ] `rg "# DECISION:"` swept into the decision log.
- [ ] README's first paragraph is the thesis, not "This project implements…".
- [ ] `CITATIONS.md` complete — papers, model cards, snippets, prompt patterns, the dataset licence.
- [ ] `report/traces.html` opens with a double-click and looks good.
- [ ] The report is ≤6 pages and its best section is "what is misleading about my headline number."
- [ ] One memorised failure example, one memorised number, one memorised limitation.
