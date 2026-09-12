"""Renders report/traces.html: one filterable card per golden item. BUILD_SPEC.md §10 item 2.

"This is how you prove the system is real in 30 seconds of a reviewer's time." Plain HTML + a
little inline JS, no build step, no CDN -- filter by stratum and by correct/incorrect entirely
client-side via data-* attributes and el.hidden.
"""
from __future__ import annotations

import html

PAGE_CSS = """
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
.card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 4px; }
.pass { background: #d4f7d4; } .fail { background: #f7d4d4; } .synthetic { background: #ffe9b3; }
.controls { position: sticky; top: 0; background: white; padding: 1rem 0; border-bottom: 1px solid #ccc; }
table { border-collapse: collapse; } th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: center; }
"""

PAGE_JS = """
function applyFilters() {
  const stratum = document.getElementById('stratum-filter').value;
  const correctness = document.getElementById('correct-filter').value;
  document.querySelectorAll('.card').forEach(card => {
    const matchStratum = stratum === 'all' || card.dataset.stratum === stratum;
    const matchCorrect = correctness === 'all' || card.dataset.correct === correctness;
    card.hidden = !(matchStratum && matchCorrect);
  });
}
"""


def _esc(text: str | None) -> str:
    return html.escape(text or "")


def _card_html(record: dict) -> str:
    item, trace, judge, correct = record["item"], record["trace"], record["judge_scores"], record["correct"]
    exemplars = "".join(
        f"<li><b>sim={r.similarity:.2f}</b> cust: {_esc(r.customer_message)}<br>"
        f"agent: {_esc(r.agent_reply)}</li>" for r in trace.retrieved
    ) or "<li>(none)</li>"
    violations = (", ".join(trace.linter.violations) if trace.linter and trace.linter.violations
                  else "(clean)")
    claims = "".join(f"<li>[{c.verdict}] {_esc(c.claim)}</li>" for c in trace.claim_check.claims) \
        if trace.claim_check else "(not computed -- hard override)"
    risk = (f"{trace.risk_score.score:.2f} ({trace.risk_score.weights_source})"
            if trace.risk_score else "N/A (hard override)")
    judge_html = ", ".join(f"{k}={v}" for k, v in judge.items()) if judge else "(no draft to score)"
    synth_pill = ('<span class="pill synthetic">synthetic</span>' if item.get("synthetic") else "")

    return f"""
<div class="card" data-stratum="{item['stratum']}" data-correct="{'1' if correct else '0'}">
  <div><span class="pill {'pass' if correct else 'fail'}">{'PASS' if correct else 'FAIL'}</span>
    <span class="pill">{item['stratum']}</span>{synth_pill}</div>
  <p><b>Message:</b> {_esc(item['customer_message'])}</p>
  <p><b>Gold:</b> intent={_esc(item['intent'])} escalate={item['should_escalate']}</p>
  <p><b>Predicted:</b> intent={_esc(trace.intent_pred)} margin={trace.margin:.2f}</p>
  <details><summary>Retrieved exemplars ({len(trace.retrieved)})</summary><ul>{exemplars}</ul></details>
  <p><b>Draft:</b> {_esc(trace.draft_final)}</p>
  <p><b>Linter:</b> {violations}</p>
  <details><summary>Claim check</summary><ul>{claims}</ul></details>
  <p><b>Risk score:</b> {risk}</p>
  <p><b>Decision:</b> {trace.decision} -- {_esc(trace.decision_reason)}</p>
  <p><b>Judge:</b> {judge_html}</p>
</div>"""


def render_traces_html(records: list[dict], header: str) -> str:
    strata = sorted({r["item"]["stratum"] for r in records})
    stratum_options = "".join(f'<option value="{s}">{s}</option>' for s in strata)
    n_correct = sum(1 for r in records if r["correct"])
    cards = "".join(_card_html(r) for r in records)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>CORDON traces</title><style>{PAGE_CSS}</style></head><body>
<h1>CORDON traces</h1>
<p>{header} | {len(records)} items | {n_correct}/{len(records)} correct</p>
<div class="controls">
  <label>Stratum: <select id="stratum-filter" onchange="applyFilters()">
    <option value="all">all</option>{stratum_options}</select></label>
  &nbsp;
  <label>Correctness: <select id="correct-filter" onchange="applyFilters()">
    <option value="all">all</option><option value="1">correct</option><option value="0">incorrect</option>
  </select></label>
</div>
{cards}
<script>{PAGE_JS}</script>
</body></html>"""
