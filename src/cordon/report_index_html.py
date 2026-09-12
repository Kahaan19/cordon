"""Renders report/index.html: coverage-risk curve, cost-sensitivity plot, confusion matrix,
judge-agreement table. BUILD_SPEC.md §10 item 3.

No charting library, no CDN -- small hand-rolled inline SVG line charts. Sections that need
data not yet collected (bad_to_autosend for coverage/cost-sensitivity; 80 human-scored items
for judge agreement) render an honest "not yet available" state, never a fabricated number.
"""
from __future__ import annotations

from cordon.report_traces_html import PAGE_CSS


def _svg_line_chart(points: list[tuple[float, float]], width: int = 420, height: int = 260,
                     x_label: str = "", y_label: str = "") -> str:
    if not points:
        return "<p>(no data)</p>"
    xs, ys = zip(*points)
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = 0.0, max(max(ys), 0.01)
    pad = 45

    def sx(x: float) -> float:
        return pad + (x - x_min) / (x_max - x_min + 1e-9) * (width - 2 * pad)

    def sy(y: float) -> float:
        return height - pad - (y - y_min) / (y_max - y_min + 1e-9) * (height - 2 * pad)

    polyline = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
    circles = "".join(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3" fill="steelblue"/>'
                       for x, y in points)
    return f"""<svg width="{width}" height="{height}" style="border:1px solid #ddd">
  <polyline points="{polyline}" fill="none" stroke="steelblue" stroke-width="2"/>
  {circles}
  <text x="{width / 2}" y="{height - 8}" text-anchor="middle" font-size="12">{x_label}</text>
  <text x="12" y="{height / 2}" text-anchor="middle" font-size="12"
        transform="rotate(-90,12,{height / 2})">{y_label}</text>
</svg>"""


def _confusion_table(confusion: dict) -> str:
    labels = list(confusion.keys())
    header = "<tr><th>true \\ pred</th>" + "".join(f"<th>{p}</th>" for p in labels) + "</tr>"
    rows = "".join(
        f"<tr><th>{t}</th>" + "".join(f"<td>{confusion[t][p]}</td>" for p in labels) + "</tr>"
        for t in labels
    )
    return f"<table>{header}{rows}</table>"


def _coverage_section(coverage_curve: list[dict] | None) -> str:
    if coverage_curve is None:
        return ("<p><i>Not yet available -- needs bad_to_autosend, a separate blind labelling "
                "pass collected after every system has run on the golden set "
                "(docs/ANNOTATION_GUIDE.md §3).</i></p>")
    points = [(c["alpha"], c["coverage"]) for c in coverage_curve]
    return _svg_line_chart(points, x_label="risk budget (alpha)", y_label="coverage")


def _cost_sensitivity_section(cost_sensitivity: list[dict] | None) -> str:
    if cost_sensitivity is None:
        return "<p><i>Not yet available -- same dependency as the coverage-risk curve above.</i></p>"
    rows = "".join(
        f"<tr><td>{c['cost_ratio']}</td><td>{c['optimal_tau']:.3f}</td>"
        f"<td>{c['expected_saving']:.3f}</td></tr>" for c in cost_sensitivity
    )
    return (f"<table><tr><th>C_b</th><th>optimal tau</th><th>expected saving</th></tr>{rows}"
            "</table>")


def _judge_agreement_section(judge_agreement: list | None) -> str:
    if judge_agreement is None:
        return ("<p><i>Not yet available -- needs 80 human-scored replies, blind to system "
                "(BUILD_SPEC.md §9.4.1). Not yet collected.</i></p>")
    return f"<p>{len(judge_agreement)} human-scored items available.</p>"


def render_index_html(confusion: dict, coverage_curve: list[dict] | None,
                       cost_sensitivity: list[dict] | None, judge_agreement: list | None,
                       header: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>CORDON evaluation</title><style>{PAGE_CSS}</style></head><body>
<h1>CORDON evaluation</h1>
<p>{header}</p>
<h2>Coverage-risk curve</h2>
{_coverage_section(coverage_curve)}
<h2>Cost-sensitivity (optimal threshold vs. bad-reply cost)</h2>
{_cost_sensitivity_section(cost_sensitivity)}
<h2>Confusion matrix (intent)</h2>
{_confusion_table(confusion)}
<h2>Judge agreement</h2>
{_judge_agreement_section(judge_agreement)}
</body></html>"""
