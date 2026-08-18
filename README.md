# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 3 of 10 complete.

---

## Problem Statement

In large, professional companies, code review is handled by separate specialized departments — QA/testing, security, code quality/standards, plus roles covering test coverage, documentation, performance, and dependency management.

Small startups and solo developers don't have this luxury. One person (or a tiny team) has to handle all of it alone, which leads to rushed or skipped reviews, bugs and security issues slipping into production, declining code quality over time, and bottlenecks when only one senior developer is available.

This project solves that by building an AI system that acts as a full, always-available review team — instantly reviewing GitHub Pull Requests with the rigor of a large company's multiple departments, without needing to hire more people.

---

## Scope & Limitations

**This project currently reviews Python (`.py`) code only.**

Every static analysis tool planned for the specialist agents — `pylint`, `flake8`, `bandit`, `coverage.py`, `radon`, `pip-audit`, and the `ast`-based documentation check — is Python-specific. A PR that changes non-Python files will still be fetched in full, but only `.py` files are sent to the language-specific specialist agents for review. Non-Python files are explicitly filtered out and tracked (not silently dropped), so the Coordinator's final report (Day 6) will always list what was and wasn't reviewed.

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
   │  2. Security Agent                       │  ⏳ planned (Day 4)
   │  3. Style/Readability Agent              │  ⏳ planned (Day 4)
   │  4. Test Coverage Agent                  │  ⏳ planned (Day 4)
   │  5. Documentation Agent                  │  ⏳ planned (Day 5)
   │  6. Performance Agent                    │  ⏳ planned (Day 5)
   │  7. Dependency/License Agent              │  ⏳ planned (Day 5)
   │  (each = static analysis tool + LLM,     │
   │   all traced live in LangSmith)          │
   └────────────────┬─────────────────────────┘
                     ↓
              Coordinator Agent                  ⏳ planned (Day 6)
   (merges findings, resolves conflicts/duplicates,
    prioritizes issues, writes final verdict)
                     ↓
         Final Report (FastAPI + Streamlit)       ⏳ planned (Days 7-8)
         + Full reasoning trace in LangSmith
```

Each specialist agent combines the output of a **real static analysis tool** with **LLM reasoning** to explain findings in plain, human-readable language — this isn't "just prompting an LLM," it's real tooling plus AI interpretation, similar to how production tools like CodeRabbit and Sourcery work.

---

## Automated Evaluation Framework

Rather than only testing agents by hand, this project includes a **fixture-based evaluation harness** (`eval_runner.py`) built once, generically, so every new agent plugs in with zero framework changes:

- Each agent gets a library of test cases under `test_fixtures/<agent_name>/` — deliberately buggy/vulnerable code paired with a hand-written "expected findings" JSON file.
- Fixtures follow a 3-case pattern: an **obvious** issue, a **subtle** issue (stress-tests whether the agent goes beyond what its paired tool flags outright), and a **clean-code control case** (tests for false positives).
- Since an agent's report is natural language, not a clean checklist, grading uses **LLM-as-judge**: a separate, strict grading LLM call checks whether each expected finding is actually covered by the agent's report.
- Running `python eval_runner.py <agent_name>` produces a scorecard: known issues caught (recall %) and false positives on clean code.

This turns "does this agent actually work well?" from a subjective impression into a number you can track — and it's what will power a real accuracy scorecard in this README as more agents are built.

**Current fixture coverage:** Bug-Hunter (3 cases: empty-list crash, mutable default argument, clean code control).

---

## Tech Stack (100% Free Tools)

| Layer | Tool |
|---|---|
| Agent Orchestration | LangGraph |
| LLM | Groq API (Llama 3.3 70B), Gemini API as fallback |
| Code Parsing | Python `ast` module |
| PR Fetching | PyGithub |
| Static Analysis | `pylint`, `flake8`, `bandit`, `coverage.py`, `radon`, `pip-audit` |
| Backend | FastAPI |
| Frontend | Streamlit |
| Observability | LangSmith |
| Evaluation | Custom fixture-based harness (LLM-as-judge) |
| Hosting | Streamlit Community Cloud (frontend), Render / Hugging Face Spaces (backend) |

---

## Project Progress

| Day | Focus | Status |
|---|---|---|
| 1 | Environment setup, accounts, folder structure | ✅ Done |
| 2 | GitHub fetcher (diff + old + new code) | ✅ Done |
| 3 | Bug-Hunter Agent + automated evaluation framework | ✅ Done |
| 4 | Security, Style, Test Coverage Agents | ⏳ Next |
| 5 | Documentation, Performance, Dependency Agents | ⏳ Planned |
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
│   └── bug_hunter.py           # ✅ Bug-Hunter agent (pylint + flake8 + LLM)
├── test_fixtures/
│   └── bug_hunter/             # ✅ 3 fixture cases + expected-findings JSON
├── eval_runner.py               # ✅ automated fixture-based evaluation harness
├── github_fetcher.py            # ✅ pulls PR diff + old/new code via PyGithub
├── graph.py                      # LangGraph workflow (built Day 6)
├── app.py                        # Streamlit frontend (built Day 8)
├── requirements.txt
├── .env                           # your secret keys (never committed)
├── .env.example                    # safe template of required keys
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


### 5. Try the GitHub fetcher
Set `TEST_PR_URL` in your `.env` to any real GitHub PR link, then run:
```bash
python github_fetcher.py
```
This prints a clean summary of every changed file in that PR, including old code, new code, and diff.

### 6. Try the Bug-Hunter agent
```bash
python agents/bug_hunter.py
```
Runs pylint + flake8 on the first Python file in your test PR, then asks the LLM to turn the raw tool output into a plain-English bug report. Check [smith.langchain.com](https://smith.langchain.com) afterward to see the full reasoning trace.

### 7. Run the automated evaluation suite
```bash
python eval_runner.py bug_hunter
```
Runs Bug-Hunter against its fixture library and prints a recall/false-positive scorecard.

---

## What's Working So Far

- ✅ Full local dev environment with Groq + Gemini + LangSmith wired up and verified
- ✅ `github_fetcher.py` — given any PR link, returns a structured `file_context` object per changed file:
  ```python
  {
      "filename": "balance.py",
      "old_code": "...",
      "new_code": "...",
      "diff": "...",
      "status": "modified"
  }
  ```
- ✅ `filter_python_files()` — splits fetched files into Python files (sent to agents) vs. non-Python files (skipped, but tracked and reportable)
- ✅ **Bug-Hunter Agent** — pairs `pylint` + `flake8` output with LLM reasoning to catch logic errors, runtime issues, and broken functionality; scoped strictly to that lane
- ✅ **Automated evaluation framework** (`eval_runner.py`) — fixture-based, LLM-as-judge grading, generic enough that every future agent plugs in with zero framework changes

---

## Roadmap / Next Steps

- [ ] Build the remaining 6 specialist agents (Security, Style, Test Coverage, Documentation, Performance, Dependency), each with its own fixture-based eval cases
- [ ] Build the Coordinator Agent to merge, prioritize findings, and report skipped files
- [ ] Wire everything together with LangGraph
- [ ] Expose the pipeline via a FastAPI `/review` endpoint
- [ ] Build a Streamlit demo UI
- [ ] Stress-test with real PRs and debug using LangSmith traces
- [ ] Deploy and finalize documentation with architecture diagram, screenshots, and live demo link
- [ ] **Future work:** multi-language support (ESLint for JS/TS, Semgrep for cross-language security scanning)
- [ ] **Future work:** sequential agent communication (agents referencing each other's findings)

---

## License

This project is open source and available for anyone to reference or build on. (Add your preferred license here, e.g. MIT.)