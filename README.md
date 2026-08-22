# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 4 of 10 complete.

---

## Problem Statement

In large, professional companies, code review is handled by separate specialized departments — QA/testing, security, code quality/standards, plus roles covering test coverage, documentation, performance, and dependency management.

Small startups and solo developers don't have this luxury. One person (or a tiny team) has to handle all of it alone, which leads to rushed or skipped reviews, bugs and security issues slipping into production, declining code quality over time, and bottlenecks when only one senior developer is available.

This project solves that by building an AI system that acts as a full, always-available review team — instantly reviewing GitHub Pull Requests with the rigor of a large company's multiple departments, without needing to hire more people.

---

## Scope & Limitations

**This project currently reviews Python (`.py`) code only.**

Every static analysis tool used by the specialist agents — `pylint`, `flake8`, `bandit`, `coverage.py`, `radon`, `pip-audit`, and the `ast`-based documentation check (Day 5) — is Python-specific. A PR that changes non-Python files will still be fetched in full, but only `.py` files are sent to the language-specific specialist agents for review. Non-Python files are explicitly filtered out and tracked (not silently dropped), so the Coordinator's final report (Day 6) will always list what was and wasn't reviewed.

**One deliberate exception:** the Security agent's secret/credential-leak check runs on **every file, regardless of language** — a leaked API key or a committed `.env` file doesn't care what language the surrounding project is written in.

Multi-language support (e.g. ESLint for JS/TS) is a planned Future Work item, not part of the current build.

---

## How It Works (Planned Full Pipeline)

```
GitHub PR Link (input)
        ↓
PyGithub fetches diff + old code + new code   ✅ built (Day 2)
        ↓
Filter: Python files → agents | non-Python → skipped list   ⏳ planned (Day 6)
        ↓
   ┌────────────────────────────────────────┐
   │     7 Specialist Agents (parallel)       │  🚧 in progress
   │  1. Bug-Hunter Agent                     │  ✅ built + evaluated (Day 3)
   │  2. Security Agent*                      │  ✅ built + evaluated (Day 4)
   │  3. Style/Readability Agent              │  ✅ built + evaluated (Day 4)
   │  4. Test Coverage Agent                  │  ✅ built + evaluated (Day 4)
   │  5. Documentation Agent                  │  ⏳ planned (Day 5)
   │  6. Performance Agent                    │  ⏳ planned (Day 5)
   │  7. Dependency/License Agent               │  ⏳ planned (Day 5)
   │  (each = static analysis tool + LLM,     │
   │   all traced live in LangSmith)          │
   │                                            │
   │  *Security Agent also scans ALL changed   │
   │   files (any language) for secrets/keys   │
   │   accidentally committed to the PR        │
   └────────────────┬─────────────────────────┘
                     ↓
              Coordinator Agent                  ⏳ planned (Day 6)
   (merges findings, resolves conflicts/duplicates,
    prioritizes issues, notes skipped files,
    writes final verdict)
                     ↓
         Final Report (FastAPI + Streamlit)       ⏳ planned (Days 7-8)
         + Full reasoning trace in LangSmith
```

Each specialist agent combines the output of a **real static analysis tool** with **LLM reasoning** to explain findings in plain, human-readable language — this isn't "just prompting an LLM," it's real tooling plus AI interpretation, similar to how production tools like CodeRabbit and Sourcery work.

### Security Agent — Secret & Credential Protection

Beyond pairing with `bandit` for vulnerable code patterns, the Security agent includes a dedicated, **deterministic** check (not left to LLM judgment) that:

- Flags known-risky filenames committed in the PR — `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, `service-account*.json`, etc. (`.env.example` is allowed)
- Scans file contents/diffs for patterns that look like live secrets — AWS access keys, generic API key/token assignments, private key headers, hardcoded passwords
- When something is found, the report is specific and actionable, e.g.: *"🚨 `.env` appears to have been committed — this likely contains live secrets. Remove it with `git rm --cached .env`, rotate any exposed keys immediately, and confirm `.env` is in `.gitignore`."*

---

## Automated Evaluation Framework

Rather than only testing agents by hand, this project includes a **fixture-based evaluation harness** (`eval_runner.py`) built once, generically, so every new agent plugs in with zero framework changes:

- Each agent gets a library of test cases under `test_fixtures/<agent_name>/` — deliberately buggy/vulnerable code paired with a hand-written "expected findings" JSON file.
- Fixtures generally follow a 3-case pattern: an **obvious** issue, a **subtle** issue (stress-tests whether the agent goes beyond what its paired tool flags outright), and a **clean-code control case** (tests for false positives). The Security agent gets a 4th case specifically for the leaked-`.env`-file scenario.
- Since an agent's report is natural language, not a clean checklist, grading uses **LLM-as-judge**: a separate, strict grading LLM call checks whether each expected finding is actually covered by the agent's report.
- Running `python eval_runner.py <agent_name>` produces a scorecard: known issues caught (recall %) and false positives on clean code. Running `python eval_runner.py` with no argument runs every registered agent at once.

**Reliability / consistency checking (`--runs`):** LLMs aren't perfectly deterministic even at `temperature=0` — the same fixture can occasionally produce a different result across runs. A recall score based on a single run tells you what happened *that one time*, not how reliable the agent actually is. `eval_runner.py` supports running each fixture case multiple times:

```bash
python eval_runner.py security --runs 3
```

Each expected finding is scored on majority vote across the runs, and any case where the runs disagreed with each other is flagged as **flaky** and printed by name. The default stays at 1 run for fast day-to-day iteration; `--runs 3` (or more) is meant for when a score is about to be quoted somewhere (README, interview) and needs to hold up statistically, not just anecdotally.

**Current fixture coverage (4 agents, 13 cases):**

| Agent | Cases | What's tested |
|---|---|---|
| Bug-Hunter | 3 | Empty-list crash, mutable default argument, clean code control |
| Security | 4 | SQL injection, hardcoded API key, leaked `.env` file, secure code control |
| Style | 3 | Bad naming/formatting, deep nesting, clean PEP8 control |
| Test Coverage | 3 | No tests, incomplete edge-case tests, fully tested control |

---

## Tech Stack (100% Free Tools)

| Layer | Tool |
|---|---|
| Agent Orchestration | LangGraph |
| LLM | Groq API (`openai/gpt-oss-120b`), Gemini API as fallback |
| Code Parsing | Python `ast` module |
| PR Fetching | PyGithub |
| Static Analysis | `pylint`, `flake8`, `bandit`, `coverage.py`, `black`, `pytest`, `radon`, `pip-audit` |
| Backend | FastAPI |
| Frontend | Streamlit |
| Observability | LangSmith |
| Evaluation | Custom fixture-based harness (LLM-as-judge, with multi-run reliability checking) |
| Hosting | Streamlit Community Cloud (frontend), Render / Hugging Face Spaces (backend) |

> **Note:** Groq deprecated `llama-3.3-70b-versatile` (decommissioned August 16, 2026). All agents now use `openai/gpt-oss-120b`, Groq's recommended free-tier replacement.

---

## Project Progress

| Day | Focus | Status |
|---|---|---|
| 1 | Environment setup, accounts, folder structure | ✅ Done |
| 2 | GitHub fetcher (diff + old + new code) | ✅ Done |
| 3 | Bug-Hunter Agent + automated evaluation framework | ✅ Done |
| 4 | Security, Style, Test Coverage Agents | ✅ Done |
| 5 | Documentation, Performance, Dependency Agents | ⏳ Next |
| 6 | Coordinator Agent + LangGraph orchestration | ⏳ Planned |
| 7 | FastAPI backend | ⏳ Planned |
| 8 | Streamlit frontend | ⏳ Planned |
| 9 | Testing, debugging via LangSmith | ⏳ Planned |
| 10 | Deployment + portfolio polish | ⏳ Planned |

---

## Current Folder Structure

```
multi-agent-code-review/
├── agents/
│   ├── __init__.py
│   ├── bug_hunter.py            # ✅ pylint + flake8 + LLM
│   ├── security.py               # ✅ bandit + secret/credential-leak scan + LLM
│   ├── style.py                   # ✅ pylint (convention/refactor) + black --check + LLM
│   └── test_coverage.py           # ✅ ast heuristic + self-contained coverage.py + LLM
├── test_fixtures/
│   ├── bug_hunter/                # ✅ 3 fixture cases
│   ├── security/                   # ✅ 4 fixture cases (incl. leaked .env)
│   ├── style/                       # ✅ 3 fixture cases
│   └── test_coverage/                # ✅ 3 fixture cases
├── eval_runner.py                     # ✅ automated fixture-based evaluation harness (supports --runs)
├── github_fetcher.py                   # ✅ pulls PR diff + old/new code via PyGithub
├── graph.py                              # LangGraph workflow (built Day 6)
├── app.py                                  # Streamlit frontend (built Day 8)
├── requirements.txt
├── .env                                     # your secret keys (never committed)
├── .env.example                              # safe template of required keys
└── .gitignore
```

---

## Setup Instructions

### 1. Clone the repo
```bash
git clone https://github.com/YOUR-USERNAME/multi-agent-code-review.git
cd multi-agent-code-review
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\Activate.ps1     # Windows PowerShell
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up your environment variables
Copy the template and fill in your own keys:
```bash
cp .env.example .env
```

You'll need free API keys from:
- [Groq](https://console.groq.com) — primary LLM
- [Google AI Studio](https://aistudio.google.com) — Gemini fallback LLM
- [LangSmith](https://smith.langchain.com) — tracing/observability
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (classic, `repo` scope) — needed to fetch PR data

### 5. Verify the setup
```bash
python hello_world.py
```
This confirms your Groq API connection and LangSmith tracing both work.

### 6. Try the GitHub fetcher
Set `TEST_PR_URL` in your `.env` to any real GitHub PR link, then run:
```bash
python github_fetcher.py
```

### 7. Try any specialist agent
```bash
python agents/bug_hunter.py
python agents/security.py
python agents/style.py
python agents/test_coverage.py
```
Each prints a plain-English findings report for the first Python file in your test PR. Check [smith.langchain.com](https://smith.langchain.com) afterward to see the full reasoning trace for any run.

### 8. Run the automated evaluation suite
```bash
python eval_runner.py                # all 4 agents built so far
python eval_runner.py security        # just one agent
python eval_runner.py security --runs 3   # reliability check, 3 runs per case
```
Prints a recall/false-positive scorecard per agent against its fixture library.

---

## What's Working So Far

- ✅ Full local dev environment with Groq + Gemini + LangSmith wired up and verified
- ✅ `github_fetcher.py` — given any PR link, returns a structured `file_context` object per changed file
- ✅ `filter_python_files()` — splits fetched files into Python files (sent to agents) vs. non-Python files (skipped, but tracked and reportable)
- ✅ **4 of 7 specialist agents built and evaluated:**
  - **Bug-Hunter** — `pylint` + `flake8` + LLM, catches logic errors and runtime issues
  - **Security** — `bandit` + a dedicated secret/credential-leak scanner (filenames + content patterns), catches vulnerabilities and accidentally committed secrets
  - **Style** — `pylint` (convention/refactor only) + `black --check` + LLM, catches naming/formatting/readability issues
  - **Test Coverage** — `ast` heuristic + self-contained `pytest`/`coverage.py` run + LLM, catches untested functions and missing edge cases, with an honestly documented scope limitation (can't see tests in separate files)
- ✅ **Automated evaluation framework** (`eval_runner.py`) — fixture-based, LLM-as-judge grading, with multi-run reliability/consistency checking via `--runs`; now covering 13 test cases across 4 agents

---

## Roadmap / Next Steps

- [ ] Build the final 3 specialist agents (Documentation, Performance, Dependency), each with its own fixture-based eval cases — completes all 7 agents
- [ ] Build the Coordinator Agent to merge, prioritize findings, and report skipped files
- [ ] Wire everything together with LangGraph, including routing exceptions for Security's cross-language secret scan and Dependency's manifest-file routing
- [ ] Expose the pipeline via a FastAPI `/review` endpoint
- [ ] Build a Streamlit demo UI
- [ ] Stress-test with real PRs and debug using LangSmith traces
- [ ] Deploy and finalize documentation with architecture diagram, screenshots, and live demo link
- [ ] **Future work:** multi-language support (ESLint for JS/TS, Semgrep for cross-language security scanning)
- [ ] **Future work:** sequential agent communication (agents referencing each other's findings)

---

## License

This project is open source and available for anyone to reference or build on. (Add your preferred license here, e.g. MIT.)