Classify this customer support message for {{BRAND}} against the intent taxonomy below. Pick
the single best-fitting intent, plus a runner-up, plus five orthogonal axes.

Taxonomy:
{{TAXONOMY}}

Customer message:
{{MESSAGE}}

Respond with JSON only:
- `intent`: the id of the best-fitting intent above.
- `runner_up`: the id of the second-best-fitting intent (different from `intent`).
- `confidence`: your probability (0-1) that `intent` is correct.
- `runner_up_confidence`: your probability (0-1) that `runner_up` is correct.
- `needs_account_access`: true iff a stranger with no access to this customer's account could
  NOT fully answer this — the single strongest escalation signal.
- `severity`: `"low"` / `"med"` / `"high"` — high means money lost, service unusable, safety,
  or public reputational risk.
- `anger`: `0` (neutral), `1` (frustrated), or `2` (hostile/abusive).
- `contains_pii`: true if the message itself contains an order number, email, phone, address,
  full name, booking reference, or card fragment.
- `multi_intent`: true iff a second, distinct intent would need its own separate answer.
