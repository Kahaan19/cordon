"""Deterministic draft linter. BUILD_SPEC.md §7.3(a).

Pure Python, free, zero LLM calls. Rules: char limit; sign-off present (only when the voice
profile shows the brand actually uses one -- hulu_support's signoff_rate is 0.0, so enforcing
this unconditionally would flag every single draft; docs/DECISION_LOG.md); no PII request
pattern; no promise pattern; no URL absent from the evidence block; no @handle other than the
customer placeholder.

Runs alone: `python -m cordon.linter --help` (smoke-tests two hardcoded examples).
"""
from __future__ import annotations

import argparse
import re

MAX_CHARS = 280
SIGNOFF_RE = re.compile(r"\^[A-Za-z]{1,3}\b")
SIGNOFF_RATE_THRESHOLD = 0.3
PII_REQUEST_RE = re.compile(
    r"\b(what('s| is) your (email|phone|card|account number)|"
    r"(please |can you )?(send|provide|share) (your|us your) "
    r"(email|phone|card|account number|social security))\b", re.IGNORECASE)
PROMISE_WITHIN_RE = re.compile(r"\bwithin \d+ (hour|hours|day|days)\b", re.IGNORECASE)
PROMISE_REFUND_FUTURE_RE = re.compile(r"\brefund\b.{0,20}\b(will|going to|shall)\b", re.IGNORECASE)
PROMISE_GUARANTEE_RE = re.compile(r"\bguarantee\b", re.IGNORECASE)
URL_TOKEN = "<url>"
HANDLE_RE = re.compile(r"@\w+")


def lint_draft(draft: str, evidence_text: str, voice_profile: dict) -> list[str]:
    """Returns a list of violation codes -- empty if the draft is clean."""
    violations = []
    if len(draft) > MAX_CHARS:
        violations.append("too_long")
    if voice_profile.get("signoff_rate", 0) > SIGNOFF_RATE_THRESHOLD and not SIGNOFF_RE.search(draft):
        violations.append("missing_signoff")
    if PII_REQUEST_RE.search(draft):
        violations.append("pii_request")
    if (PROMISE_WITHIN_RE.search(draft) or PROMISE_REFUND_FUTURE_RE.search(draft)
            or PROMISE_GUARANTEE_RE.search(draft)):
        violations.append("unbounded_promise")
    if URL_TOKEN in draft and URL_TOKEN not in evidence_text:
        violations.append("url_not_in_evidence")
    if set(HANDLE_RE.findall(draft)) - {"@user"}:
        violations.append("unauthorized_handle")
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the deterministic draft linter")
    parser.parse_args()
    examples = [
        ("Sorry to hear that! Please try restarting the app and check <url> for more steps.",
         "<url> is our help page"),
        ("We guarantee this will be fixed within 3 days -- a refund will be given. Please send "
         "your card details to @randomuser, see <url>.", "no links here"),
    ]
    for draft, evidence in examples:
        violations = lint_draft(draft, evidence, voice_profile={"signoff_rate": 0.9})
        print(f"{violations}: {draft[:70]}...")


if __name__ == "__main__":
    main()
