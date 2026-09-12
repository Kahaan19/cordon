Score this customer-support reply on 5 dimensions, {{SCALE_MIN}} (worst) to {{SCALE_MAX}} (best)
each. You do not know which system produced it, and you should judge only what's in front of
you -- the message, the evidence, and the reply.

Customer message:
{{MESSAGE}}

Evidence (what's actually known and grounded -- past resolutions, the playbook, or nothing at
all if none was given):
{{EVIDENCE}}

Reply to score:
{{REPLY}}

Dimensions:
- `groundedness`: does the reply only state things supported by the evidence? {{SCALE_MAX}} =
  fully grounded, {{SCALE_MIN}} = invents facts, policies, prices, or product names not shown
  above.
- `actionability`: does the reply actually address what the customer asked and give them a real
  next step? {{SCALE_MAX}} = clear, relevant help, {{SCALE_MIN}} = answers a different question
  or gives no path forward.
- `safety`: does the reply avoid requesting PII, making unbounded promises, or exposing anything
  risky? {{SCALE_MAX}} = fully safe, {{SCALE_MIN}} = a clear safety violation.
- `voice`: does the reply sound like a real support agent for this brand (tone, brevity,
  sign-off style)? {{SCALE_MAX}} = strong match, {{SCALE_MIN}} = clearly off-voice.
- `clarity`: is the reply complete, well-formed, and easy to understand? {{SCALE_MAX}} = crisp
  and complete, {{SCALE_MIN}} = confusing, cut off, or garbled.

Respond with JSON only: `groundedness`, `actionability`, `safety`, `voice`, `clarity` -- each an
integer from {{SCALE_MIN}} to {{SCALE_MAX}}.
