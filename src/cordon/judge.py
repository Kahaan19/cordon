"""The judge: local, unlimited, genuinely different weights from the Gemini generator.
BUILD_SPEC.md §9.3-9.4.

Two primitives: score_reply (the 5-dimension rubric) and compare_pair (pairwise preference, for
the position-bias probe). judge_validation.py builds the trap set and bias probes on top of
these -- this module is just the judge's core capability.

Runs alone: `python -m cordon.judge --help` (smoke-tests one good and one bad reply).
"""
from __future__ import annotations

import argparse

from rich.console import Console

from config import RUBRIC_DIMENSIONS, RUBRIC_SCALE_MAX, RUBRIC_SCALE_MIN
from cordon.llm import JUDGE_MODEL, complete, load_prompt

console = Console()

RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {d: {"type": "integer"} for d in RUBRIC_DIMENSIONS},
    "required": RUBRIC_DIMENSIONS,
}

PAIRWISE_SCHEMA = {
    "type": "object",
    "properties": {"winner": {"type": "string", "enum": ["A", "B", "tie"]}},
    "required": ["winner"],
}


def score_reply(message: str, evidence: str, reply: str, cache: bool = True) -> dict[str, int]:
    prompt = (load_prompt("judge_rubric")
              .replace("{{SCALE_MIN}}", str(RUBRIC_SCALE_MIN))
              .replace("{{SCALE_MAX}}", str(RUBRIC_SCALE_MAX))
              .replace("{{MESSAGE}}", message).replace("{{EVIDENCE}}", evidence or "(none given)")
              .replace("{{REPLY}}", reply))
    parsed = complete(prompt, model=JUDGE_MODEL, provider="ollama", schema=RUBRIC_SCHEMA,
                       cache=cache).parsed
    return {d: int(parsed[d]) for d in RUBRIC_DIMENSIONS}


def compare_pair(message: str, evidence: str, reply_a: str, reply_b: str, cache: bool = True) -> str:
    prompt = (load_prompt("judge_pairwise").replace("{{MESSAGE}}", message)
              .replace("{{EVIDENCE}}", evidence or "(none given)")
              .replace("{{REPLY_A}}", reply_a).replace("{{REPLY_B}}", reply_b))
    return complete(prompt, model=JUDGE_MODEL, provider="ollama", schema=PAIRWISE_SCHEMA,
                     cache=cache).parsed["winner"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the judge's rubric and pairwise calls")
    parser.parse_args()
    message = "my app keeps crashing when I try to watch anything"
    evidence = "Past reply: Sorry to hear that! Try uninstalling and reinstalling the app: <url>"
    good = "Sorry to hear that! Try uninstalling and reinstalling the app: <url>"
    bad = "We guarantee this will be fixed within 24 hours and will refund your account."

    console.print("good:", score_reply(message, evidence, good, cache=False))
    console.print("bad:", score_reply(message, evidence, bad, cache=False))
    console.print("pairwise (good, bad):", compare_pair(message, evidence, good, bad, cache=False))
    console.print("pairwise (bad, good):", compare_pair(message, evidence, bad, good, cache=False))


if __name__ == "__main__":
    main()
