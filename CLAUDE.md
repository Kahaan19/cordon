# CLAUDE.md — repo constitution

You are building `cordon`, described in full in `BUILD_SPEC.md`. **Read `BUILD_SPEC.md` before
every work session.** This file is the standing set of rules that override your defaults.

## The one thing to remember

This repo is graded on **proof, not on the system**. A simpler agent with an airtight evaluation
beats a clever agent with a hand-wavy one. When you have to choose between making the agent better
and making the evidence better, **make the evidence better.**

## Hard rules

1. **No number is ever hand-written into prose.** All metrics are computed by `evaluate.py` and
   written into `RESULTS.md`, stamped with git SHA, timestamp and config hash. `REPORT.md` quotes
   `RESULTS.md`. If you find yourself typing a decimal into a markdown sentence, stop.
2. **Every LLM call goes through `src/cordon/llm.py`.** No direct `google.generativeai` calls and
   no direct `ollama` HTTP calls anywhere else. The cache and the cost accounting live there and
   nowhere else. This project runs on **Gemini's free tier** (generator) **+ a local Ollama model**
   (`qwen3:8b`, judge) — deliberately zero-cost and deliberately cross-family; see `BUILD_SPEC.md`
   §2 for why. Do not reintroduce a paid API anywhere in this repo without discussing it first.
3. **`CORDON_OFFLINE=1` must make the entire evaluation runnable with no API key and no running
   Ollama daemon**, replaying the committed SQLite cache. A cache miss under that flag is a loud
   exception, never a silent API call. There is a test for this. It must never be skipped.
3a. **Gemini free-tier 429s are expected, not errors.** `llm.py` must retry with exponential
   backoff on rate-limit responses rather than surfacing them as pipeline failures. Log every
   retry; a run that silently stalls on a 429 loop is worse than one that fails loudly.
4. **Determinism.** `temperature=0` everywhere except the deliberate self-consistency sampler
   (which uses a fixed seed list). All random seeds come from `config.py`. Two runs of
   `make reproduce` must produce byte-identical `RESULTS.md` apart from the timestamp line.
5. **Time-based splits only.** Never `train_test_split(shuffle=True)` on this corpus. If you need
   a split, import it from `config.py`.
6. **No new dependencies without a line in `docs/DECISION_LOG.md`.** Forbidden outright:
   LangChain, LlamaIndex, Haystack, any vector database server, any agent framework, any
   experiment-tracking SaaS. Allowed: numpy, pandas, pyarrow, scikit-learn, scipy,
   sentence-transformers, pydantic, pyyaml, google-generativeai, ollama, pytest, matplotlib,
   jinja2, rich, python-dotenv.
7. **Cite what you borrow** in `CITATIONS.md` at the moment you borrow it — a paper, a metric
   definition, a prompt pattern, a StackOverflow snippet, a model card. The brief grades this.
8. **Every module must be runnable alone**: `python -m cordon.<module> --help` works, and each has
   a `main()` that does one thing. No god-scripts.
9. **Files stay under ~250 lines.** If a module grows past that, it is doing two jobs.
10. **Fail loudly.** No bare `except:`, no `except Exception: pass`, no silent fallback that hides
    a broken pipeline stage. A degraded path must set a flag on the `Trace` that the evaluator
    counts and reports.

## Anti-bloat

Do not add, unless `BUILD_SPEC.md` asks for it: a web UI, a FastAPI server, Docker, a database,
async everywhere, an abstract base class with one implementation, a plugin registry, a config
framework, retry decorators with exponential backoff on local functions, logging infrastructure
beyond `rich` + a single logger, type-stub packages, a `utils.py` grab-bag.

Each of these costs interview credibility: the author will be asked to explain any file in the repo
live, and cannot say "the framework does that."

## Style

- Plain functions and pydantic models. Classes only where state genuinely persists (the LLM client,
  the index).
- Docstrings say **why**, not what. The what is readable from the code.
- Comments that encode a decision get the marker `# DECISION:` so they can be grepped into the
  decision log at the end: `rg "# DECISION:"`.
- Prompts live in `src/cordon/prompts/*.md` and are loaded by name, never inlined as long
  triple-quoted strings. Prompts are artifacts a reviewer will read; make them readable.

## Definition of done for any phase

- [ ] It runs from the Makefile with one command.
- [ ] It has at least one test from the list in `BUILD_SPEC.md` §13.
- [ ] Its output is a committed, human-readable artifact (yaml/json/md/html), not just an in-memory
      object.
- [ ] Any non-obvious choice it embodies is a bullet in `docs/DECISION_LOG.md`.
- [ ] Any technique it uses is explainable in two sentences in `docs/INTERVIEW_PREP.md`.

## When you disagree with the spec

Say so, in one paragraph, before implementing. The spec was written before the data was seen; the
data wins. But a deviation must be recorded in the decision log with the evidence that caused it —
"the audit showed brand X deflects 71% of the time, so I switched to brand Y" is exactly the kind
of entry that makes the log worth reading.
