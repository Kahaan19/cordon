"""Tests 6-9 from BUILD_SPEC.md §13: linter char limit, PII request, unbounded promise,
URL-not-in-evidence."""
from __future__ import annotations

from cordon.linter import lint_draft

VOICE_NO_SIGNOFF = {"signoff_rate": 0.0}


def test_char_limit_violation():
    draft = "a" * 281
    assert "too_long" in lint_draft(draft, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)
    assert "too_long" not in lint_draft("a" * 280, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)


def test_pii_request_violation():
    draft = "Sorry about that! Can you please share your email address so we can look into it?"
    assert "pii_request" in lint_draft(draft, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)
    clean = "Sorry about that! Please try restarting the app."
    assert "pii_request" not in lint_draft(clean, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)


def test_unbounded_promise_violation():
    draft = "We guarantee this will be fixed within 3 days."
    violations = lint_draft(draft, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)
    assert "unbounded_promise" in violations
    clean = "We're looking into this, thanks for your patience."
    assert "unbounded_promise" not in lint_draft(clean, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)


def test_url_not_in_evidence_violation():
    draft = "Please check this link for help: <url>"
    assert "url_not_in_evidence" in lint_draft(draft, evidence_text="no links here",
                                                voice_profile=VOICE_NO_SIGNOFF)
    assert "url_not_in_evidence" not in lint_draft(draft, evidence_text="see <url> for steps",
                                                    voice_profile=VOICE_NO_SIGNOFF)


def test_signoff_only_required_when_brand_uses_one():
    draft = "Sorry about that, please try restarting the app."
    assert "missing_signoff" not in lint_draft(draft, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)
    assert "missing_signoff" in lint_draft(draft, evidence_text="", voice_profile={"signoff_rate": 0.9})


def test_unauthorized_handle_violation():
    draft = "Hi @user, thanks for reaching out! Also cc @randomperson for visibility."
    assert "unauthorized_handle" in lint_draft(draft, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)
    clean = "Hi @user, thanks for reaching out!"
    assert "unauthorized_handle" not in lint_draft(clean, evidence_text="", voice_profile=VOICE_NO_SIGNOFF)


def test_fabricated_literal_url_violation():
    """A real B2 baseline output invented a plausible-looking support URL. Since ingest.py's
    clean_text() always masks real URLs to <url>, evidence can never contain a literal URL --
    so any literal http(s):// in a draft is fabricated, even if it happens to match the
    <url>-in-evidence check."""
    draft = "Check our supported devices here: http://hulu.com/support/articles/200730109"
    assert "fabricated_url" in lint_draft(draft, evidence_text="<url> lists supported devices",
                                           voice_profile=VOICE_NO_SIGNOFF)
    clean = "Check our supported devices here: <url>"
    assert "fabricated_url" not in lint_draft(clean, evidence_text="<url> lists supported devices",
                                               voice_profile=VOICE_NO_SIGNOFF)
