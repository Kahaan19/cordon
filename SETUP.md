# Setup — from zero to Claude Code building CORDON

Target: MacBook Pro M4. Total setup time ~20 minutes, most of it the dataset download.

---

## 1. Prerequisites (~5 min)

```bash
# Homebrew, if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install git python@3.11
curl -LsSf https://astral.sh/uv/install.sh | sh      # uv: fast Python env manager
```

## 2. Install Claude Code (~2 min)

```bash
curl -fsSL https://claude.ai/install.sh | bash       # native installer (recommended)
# or: brew install --cask claude-code
claude --version
```

Requires a Claude Pro, Max, Team, Enterprise, or Console account — the free plan doesn't include
Claude Code. First run of `claude` opens a browser to log in. This is the only thing your Pro
subscription pays for; the pipeline itself runs on separate, free infrastructure (next step).

## 3. Get the pipeline's LLM access — $0 (~5 min)

The pipeline (`agent.py`, `judge.py`, etc.) is a separate program from Claude Code — it makes its
own model calls, and those don't come from your Claude subscription. This build uses two backends,
both free:

**Generator — Gemini API, free tier, no billing account:**
1. Go to `aistudio.google.com/apikey`, accept terms, click "Create API key". No credit card.
2. Note the current free-tier Flash model ID shown there (something like `gemini-flash-latest` or
   `gemini-2.5-flash` — it changes over time, use whatever's current).
3. Check your rate limits at `aistudio.google.com/rate-limit` so you know what `llm.py`'s
   backoff needs to handle.

**Judge — Ollama, local, on your M4, genuinely free with no rate limit:**
```bash
brew install ollama
ollama serve &          # leave running in the background, or open the Ollama.app
ollama pull qwen3:8b    # ~5GB download, one-time
ollama run qwen3:8b "say hi"   # smoke test
```
Running the judge locally on a different model family than the generator is deliberately better
than judging Gemini-with-Gemini — see `BUILD_SPEC.md` §2 and §9.4 for why, and how you measure it.

## 4. Create the repo (~2 min)

Download the files from the chat (or unzip `cordon-build-spec.zip`), then:

```bash
mkdir -p ~/code/cordon && cd ~/code/cordon
git init && mkdir -p docs data/raw report

# from wherever you saved them:
mv ~/Downloads/BUILD_SPEC.md ~/Downloads/CLAUDE.md .
mv ~/Downloads/{ANNOTATION_GUIDE,REPORT_SKELETON,DECISION_LOG,INTERVIEW_PREP,START_HERE,SETUP}.md docs/

printf '.env\ndata/raw/\ndata/interim/\n.venv/\n__pycache__/\n*.pyc\n' > .gitignore
printf 'GEMINI_API_KEY=AIza...\nOLLAMA_HOST=http://localhost:11434\n' > .env   # paste your real Gemini key

git add -A && git commit -m "Spec and scaffolding"
```

Budget: **$0**. Gemini's free tier and a local Ollama model cost nothing; the only spend risk would
be re-introducing a paid API, which `CLAUDE.md` now explicitly rules out.

## 5. Get the dataset (~10 min, 500MB)

Easiest is the browser: log in to Kaggle, open
`kaggle.com/datasets/thoughtvector/customer-support-on-twitter`, hit Download, unzip `twcs.csv`
into `data/raw/`.

Or by CLI:
```bash
uv tool install kaggle
# kaggle.com → Settings → API → "Create New Token" → saves kaggle.json
mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
kaggle datasets download -d thoughtvector/customer-support-on-twitter -p data/raw --unzip
ls -lh data/raw/twcs.csv     # expect ~500MB
```

Check the dataset's licence on that page while you're there — you need it for `CITATIONS.md` and
for deciding whether you can commit a subsample (decision-log entry).

## 6. Start Claude Code

```bash
cd ~/code/cordon
claude
```

`CLAUDE.md` in the repo root is loaded automatically into every session — that's why the rules live
there rather than in your prompts.

**First message, paste verbatim:**

> Read `BUILD_SPEC.md` and `CLAUDE.md` in full before writing anything. Then implement **Phase 0
> and Phase 1 only**: `config.py`, `schemas.py`, `src/cordon/llm.py` (cached client with a Gemini
> backend for the generator and an Ollama backend for the judge, cost/latency accounting, and the
> `CORDON_OFFLINE` guard — see BUILD_SPEC §11 for the exact contract), `src/cordon/ingest.py`,
> `src/cordon/brand_audit.py`, a Makefile with `ingest`, `audit`, `test` targets, and tests 1–5
> from §13.
>
> Stop when `make audit` writes `report/brand_audit.md`. Do not start the taxonomy. Do not add
> anything the spec doesn't ask for. Before writing code, tell me in five bullets what you're about
> to build and flag anything in the spec you think is wrong.

---

## 6. The phase prompts

One message per phase. **Commit and `/clear` between phases** — a fresh context per phase keeps the
agent from drifting and keeps it fast.

| # | Prompt (paste as-is, one per session) |
|---|---|
| 2 | "Phase 2 from BUILD_SPEC §5: `taxonomy.py`. Induce intents, produce `taxonomy/intents.yaml` with 8–10 intents plus `other`, and run the ARI stability check across 3 seeds. Show me the cluster names and sizes before you write the YAML — I'll merge them myself." |
| 3 | "Build me the labelling tool first: a single-file local HTML or terminal labeller that reads a JSONL of sampled items and writes `data/golden/golden_v1.jsonl` with the schema in docs/ANNOTATION_GUIDE.md §2. Keyboard-driven, one item per screen, autosaves. Also write the sampler that draws the 4 strata per §9.1. Nothing else." |
| 4 | "Phase 3 from §6: `index.py` and `playbook.py`. Embeddings with bge-small on MPS, numpy dot-product search, MMR diversification to 3, playbook mining per intent into `playbooks/*.json`, voice profile into `voice/`. Show me one playbook before you generate the rest." |
| 5 | "Phase 4 from §7: `agent.py`. Full Trace object, classify → retrieve → draft → linter → claim-check → self-consistency → risk score. Prompts go in `src/cordon/prompts/*.md`. Run it on 10 test messages and print the traces." |
| 6 | "Phase 5: `baselines.py` — B0a, B0b, B1, B2 per §9.2, all producing the same Trace schema as CORDON. Give B2 a genuinely fair prompt; it's the honest comparison." |
| 7 | "Phase 6a: `judge.py` — the 5-dimension rubric, the trap set with injected defects per §9.4, and the bias probes. Judge runs on local Ollama (qwen3:8b) — genuinely different weights from the Gemini generator, not just a different prompt." |
| 8 | "Phase 6b: `calibrate.py` and `evaluate.py` — Clopper–Pearson threshold search, bootstrap CIs, all metrics from §9.3, stratum reweighting. Write everything to RESULTS.md with the git SHA header." |
| 9 | "Phase 7: `report.py` — `report/traces.html` (self-contained, filterable, one card per golden item) and `report/index.html` (coverage–risk curve, confusion matrix, judge agreement). No build step, no CDN." |
| 10 | "Verify the repro path: fresh clone into /tmp, `make reproduce` with CORDON_OFFLINE=1, no API key set, Ollama not running, time it. Fix whatever breaks. Then write the README with the thesis paragraph first." |

Between phases 2 and 3 is where **you** label 200 items. Nothing else in the build competes with
that for grade value.

---

## 7. Operating Claude Code well on this project

- **`/clear` between phases.** Long contexts make the agent forget `CLAUDE.md` and start inventing.
- **Commit after every phase.** `git add -A && git commit -m "phase N"`. You want a history that
  shows incremental, explicable work — and a point to roll back to.
- **Read every file it writes.** Not skim. You will be asked to modify this code live. Any file you
  haven't read is a file that can end your interview.
- **Push back in-session.** "That's more abstraction than the spec asks for, simplify it" works, and
  keeps the repo defensible.
- **Plan mode (shift+tab twice)** before the bigger phases — you get to approve the approach before
  any code lands.
- **When it drifts,** don't argue: `/clear`, then re-paste the phase prompt with "re-read CLAUDE.md
  first".
- **Watch for the classic failure:** it will want to add retry decorators, an abstract base class,
  a FastAPI endpoint, and a `utils.py`. `CLAUDE.md` forbids all four. Enforce it.

---

## 8. Submission checklist

- [ ] `make reproduce` from a fresh clone, no API key, Ollama not running, under 15 minutes, numbers match `RESULTS.md`
- [ ] `data/golden/golden_v1.jsonl` + `relabel_v1.jsonl` committed
- [ ] `report/traces.html` opens on a double-click
- [ ] `REPORT.md` ≤ 6 pages, decision log ≥ 15 real entries, `CITATIONS.md` complete
- [ ] Repo public, or private with access granted to the reviewers
- [ ] Submitted via the Notion form (not email)
- [ ] You have read every file in `src/` and can explain each one
