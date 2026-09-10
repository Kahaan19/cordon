You merged several raw clusters into one final support intent, **{{INTENT_NAME}}**, for
{{BRAND}}. Below are the separate {name, definition, inclusion_criteria, exclusion_criteria}
written for each cluster before the merge:

{{MEMBERS}}

Write ONE clean, non-repetitive version that covers everything the members describe. Do not
invent new criteria — synthesize only what's already stated above.

Respond with JSON only:
- `definition`: one sentence, what this intent covers.
- `include`: one sentence, what makes a message belong here.
- `exclude`: one sentence, the nearest neighboring intents and why a message goes there instead.
