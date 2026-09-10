# Start here

Five files. Drop them into an empty repo and hand it to Claude Code.

| File | What it is | Who reads it |
|---|---|---|
| `BUILD_SPEC.md` | The full technical plan: thesis, data handling, seven phases, file tree, metrics, hour-by-hour schedule, cut order | You, then Claude Code, every session |
| `CLAUDE.md` | Standing rules for the coding agent — determinism, caching, forbidden dependencies, anti-bloat | Claude Code, automatically |
| `docs/ANNOTATION_GUIDE.md` | How to sample and label the 200 golden items, plus the escalation decision rule | You (this is a graded deliverable — ships in the repo) |
| `docs/REPORT_SKELETON.md` | The 6-page report with the argument pre-written and the numbers left blank | You, at hour 11 |
| `docs/DECISION_LOG.md` | 18 seeded decisions to replace with what actually happened | You, continuously |
| `docs/INTERVIEW_PREP.md` | Every technique in two sentences + the questions they'll ask | You, the night before |

---

## The 60-second version of the idea

On Twitter, brands mostly **don't** resolve issues in public — they say "please DM us." So the
obvious build (RAG over past replies, score similarity to what the brand actually said) is training
and grading a deflection machine. Prove that with a number in the first hour, then reframe:

**the product question is how much volume you can safely automate, and the deliverable is a
statistically defended answer to it.** Headline metric = *auto-handled coverage at a guaranteed
maximum bad-reply rate*, compared against baselines at matched risk. Not accuracy.

That reframe is what makes this submission unlike the pile it lands in. Everything else in the spec
— playbooks, the linter, self-consistency, the judge trap set — is there to make that one number
believable.

---

## Setup

```bash
mkdir cordon && cd cordon && git init
mkdir -p docs
# copy BUILD_SPEC.md and CLAUDE.md to the root, the rest into docs/
```

## The kickoff prompt for Claude Code

Paste this verbatim as your first message:

> Read `BUILD_SPEC.md` and `CLAUDE.md` in full before writing anything. Then implement **Phase 0
> and Phase 1 only**: `config.py`, `schemas.py`, `src/cordon/llm.py` (the cached Anthropic client
> with cost accounting and the `CORDON_OFFLINE` guard), `src/cordon/ingest.py`, and
> `src/cordon/brand_audit.py`, plus a Makefile with `data`, `ingest`, `audit` and `test` targets
> and the tests numbered 1–5 in §13.
>
> Stop when `make audit` writes `report/brand_audit.md`. Do not start the taxonomy. Do not add
> anything the spec doesn't ask for. Before you write code, tell me in five bullets what you're
> about to build and flag anything in the spec you think is wrong.

Then go phase by phase, one message each. Never say "now build the whole thing" — that is how you
end up with a repo you can't explain in the live interview.

---

## Three things that will decide your grade

1. **Protect the golden-set slot (hours 2.5–5).** 200 hand-labelled items is the deliverable that
   most candidates will fake or rush. Yours is the foundation of every other number. Label it while
   you're fresh, not at 1am.
2. **Ship `report/traces.html`.** A reviewer with eight submissions and an hour will open one file.
   Make it the one that shows every decision your system made on every test item.
3. **Verify `make reproduce` from a clean clone before you submit.** The brief says 15 minutes and
   they will time it. A committed LLM cache means it costs them nothing and gives them your exact
   numbers.

## One warning

Do not ship anything from `docs/INTERVIEW_PREP.md` Part 1 that you can't say out loud in your own
words. The statistics in this spec are all genuinely simple — Clopper–Pearson is one scipy call, the
threshold search is six lines — but "my AI assistant added it" is the worst possible answer to
"explain this." Read those six lines until they're yours.
