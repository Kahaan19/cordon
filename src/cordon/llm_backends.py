"""The two backends behind llm.py's complete(): Gemini (generator) and Ollama (judge).
BUILD_SPEC.md §11.

Split from llm.py once the combined file passed ~250 lines (same reasoning as the taxonomy.py/
taxonomy_finalize.py and agent.py/verify.py/linter.py splits): caching/dispatch is one job,
backend-specific API integration is another.
"""
from __future__ import annotations

import json
import os
import time

from rich.console import Console

from config import JUDGE_MODEL, OLLAMA_HOST_DEFAULT

console = Console()

REQUEST_TIMEOUT_MS = 60_000  # a stalled connection must fail loudly, not hang forever (rule 10)


class GeminiBackend:
    """Free-tier Gemini. 429s are expected (BUILD_SPEC.md §2, CLAUDE.md rule 3a) — retry with
    exponential backoff rather than surfacing them as pipeline failures. 503s (transient
    server-side overload, observed in practice on gemini-flash-latest) get the same treatment:
    both are "the server is busy," neither is a pipeline bug."""

    MAX_RETRIES = 10
    RETRYABLE_MARKERS = ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED")
    # DECISION: a per-day quota violation (quotaId contains "PerDay") needs a ~24h wait, not a
    # 60s-capped backoff -- retrying just burns MAX_RETRIES attempts pointlessly before failing
    # anyway. Fail immediately and loudly instead (rule 10); per-minute/transient errors still
    # get the full retry treatment. See docs/DECISION_LOG.md.
    NON_RETRYABLE_MARKERS = ("PerDay",)

    def generate(self, prompt: str, system: str, temperature: float, max_tokens: int,
                 schema: dict | None, model: str) -> tuple[str, dict | None, int, int]:
        # DECISION: google-generativeai is dead ("all support has ended", per its own
        # deprecation warning) and its auth path no longer works reliably against the current
        # API — migrated to google-genai. See docs/DECISION_LOG.md.
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set — required for a live Gemini call")
        # DECISION: explicit request timeout -- a stalled connection (e.g. the machine sleeping
        # mid-request) otherwise hangs forever with no error, no retry, no progress. Observed
        # directly: a background run sat for over an hour with ~4s of actual CPU time.
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

        config = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens,
                                              system_instruction=system or None)
        if schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = schema

        for attempt in range(self.MAX_RETRIES):
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                break
            except Exception as exc:  # DECISION: broad catch is deliberate here — the google
                # SDK raises different exception types across versions for the same transient
                # condition, and every one of them must retry, never surface as a pipeline
                # failure (rule 3a).
                text = str(exc)
                retryable = (any(m in text for m in self.RETRYABLE_MARKERS)
                             and not any(m in text for m in self.NON_RETRYABLE_MARKERS))
                if not retryable or attempt == self.MAX_RETRIES - 1:
                    raise
                wait = min(2 ** attempt, 60)
                console.log(f"[yellow]Gemini transient error, retry {attempt + 1}/"
                            f"{self.MAX_RETRIES} in {wait}s[/yellow]")
                time.sleep(wait)

        text = response.text
        parsed = json.loads(text) if schema is not None else None
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return text, parsed, input_tokens, output_tokens


class OllamaBackend:
    """Local judge, no key, no rate limit. Requires `ollama pull qwen3:8b` once (SETUP.md).

    DECISION: qwen3 is a hybrid-thinking model that, left to its defaults, puts its entire
    chain-of-thought in a separate `message.thinking` field and can burn the whole max_tokens
    budget on it -- observed empirically: a 3-word request took 56s and returned empty content
    with 1024/1024 tokens spent thinking. `think=False` disables this: same request drops to
    0.5s with content correctly populated. Every judge call here is a short, structured
    verdict (supported/unsupported/irrelevant, a rubric score) -- exactly the case thinking
    mode doesn't help and actively breaks schema-forced JSON output. See docs/DECISION_LOG.md.
    """

    def generate(self, prompt: str, system: str, temperature: float, max_tokens: int,
                 schema: dict | None, model: str) -> tuple[str, dict | None, int, int]:
        import ollama

        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", OLLAMA_HOST_DEFAULT),
                                timeout=REQUEST_TIMEOUT_MS / 1000)
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        response = client.chat(
            model=model,
            messages=messages,
            think=False,
            format=schema if schema is not None else None,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        text = response["message"]["content"]
        parsed = json.loads(text) if schema is not None else None
        input_tokens = response.get("prompt_eval_count", 0) or 0
        output_tokens = response.get("eval_count", 0) or 0
        return text, parsed, input_tokens, output_tokens


def select_provider(model: str, provider: str | None):
    if provider == "gemini" or (provider is None and model.startswith("gemini")):
        return GeminiBackend()
    if provider == "ollama" or (provider is None and model == JUDGE_MODEL):
        return OllamaBackend()
    raise ValueError(f"Cannot infer provider for model={model!r}; pass provider= explicitly")
