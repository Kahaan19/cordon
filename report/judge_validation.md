# Judge validation (BUILD_SPEC.md §9.4)

## Trap set (n=40, real substantive replies, deterministic defect injection)

| defect | dimension | detection rate |
|---|---|---|
| truncated_mid_sentence | clarity | 90% |
| pii_request | safety | 80% |
| subtly_wrong_product_name | groundedness | 72% |
| invented_policy | groundedness | 70% |
| wrong_intent | actionability | 52% |
| unbounded_promise | groundedness | 42% |
| wrong_signoff_voice | voice | 42% |

## Position-bias probe (n=15)

Flip rate: **67%** -- how often swapping which side (A/B) two replies appear on changes the pairwise winner.


## Length-bias probe (n=15)

Score delta after padding a real reply with content-free filler:

| dimension | delta |
|---|---|
| groundedness | +0.87 |
| actionability | +0.87 |
| safety | +0.00 |
| voice | +0.73 |
| clarity | +0.80 |

## Self-preference probe (n=15)

Mean rubric score (averaged across all 5 dimensions), blind, by reply source:

| source | mean score |
|---|---|
| qwen_draft | 3.80 |
| real_reply | 4.03 |
| b1_copied | 4.03 |
