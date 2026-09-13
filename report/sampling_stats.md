# Golden set sampling stats

- **natural**: 50 / 50 target
- **rare_intent**: 20 / 20 target
- **hard**: 20 / 20 target
- **redteam**: 15 / 15 target

Rare intents chosen (4 lowest-frequency per weak TF-IDF classifier): account_login_access, app_bugs_and_ui_complaints, customer_service_complaint, subscription_billing_refund

Redteam: 2 real (mined) + 13 synthetic (hand-authored, flagged synthetic=true in the JSONL) -- see docs/DECISION_LOG.md #33 for why mining alone fell short.

Redteam reason breakdown: {'abuse': 2, 'self_harm': 3, 'prompt_injection': 4, 'pii': 4, 'spam': 2}
