You're distilling how {{BRAND}} actually resolves the **{{INTENT}}** intent, from real
historical agent replies. Raw retrieval over these tweets gives *style* transfer; this file is
the *procedure* — what the brand actually does, step by step, when it isn't just deflecting.

Real substantive agent replies for this intent:

{{REPLIES}}

Respond with JSON only:
- `intent`: repeat "{{INTENT}}" back.
- `typical_steps`: ordered list of the steps agents actually take (e.g. "ask which device + OS").
- `info_agent_requests`: what info agents ask the customer for.
- `when_they_escalate_to_dm`: one sentence, the condition under which this intent moves to DM.
- `known_links_used`: any URL patterns or help-page types referenced (use `<url>` if the
  replies only show a masked link marker, not a real address).
- `phrases`: recurring brand phrases actually used.
- `never_promises`: things agents visibly avoid committing to (refund timelines, compensation,
  specific dates, etc).

Only state what these replies actually show. Do not invent steps that aren't evidenced above.
