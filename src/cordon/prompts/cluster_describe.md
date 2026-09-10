You are labelling one cluster from a KMeans clustering of customer-support tweets sent to
{{BRAND}}. Below are 15 example messages from this cluster: 12 are the messages closest to the
cluster's centroid (its core), 3 are random members (to catch outliers the centroid misses).

Read them and describe the cluster as a support **intent** — what the customer wants, not how
they phrased it.

Examples:
{{EXAMPLES}}

Respond with JSON only:
- `name`: 2-4 words, snake_case, e.g. `playback_error`, `billing_dispute`.
- `one_line_definition`: one sentence, what this intent covers.
- `inclusion_criteria`: one sentence, what makes a message belong here.
- `exclusion_criteria`: one sentence, the nearest neighboring intent and why a message goes there
  instead of here.
- `is_junk`: true if this cluster is not a coherent intent at all — spam, off-topic, praise with
  no request, or too mixed to name in one sentence. false otherwise.
