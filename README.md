# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 2 of 10 complete.

---

## Problem Statement

In large, professional companies, code review is handled by separate specialized departments — QA/testing, security, code quality/standards, plus roles covering test coverage, documentation, performance, and dependency management.

Small startups and solo developers don't have this luxury. One person (or a tiny team) has to handle all of it alone, which leads to rushed or skipped reviews, bugs and security issues slipping into production, declining code quality over time, and bottlenecks when only one senior developer is available.

This project solves that by building an AI system that acts as a full, always-available review team — instantly reviewing GitHub Pull Requests with the rigor of a large company's multiple departments, without needing to hire more people.

---

## How It Works (Planned Full Pipeline)

```
GitHub PR Link (input)
        ↓
PyGithub fetches diff + old code + new code   ✅ built (Day 2)
        ↓
   ┌────────────────────────────────────────┐
   │     7 Specialist Agents (parallel)       │  🚧 in progress (Days 3-5)
   │  1. Bug-Hunter Agent                     │
   │  2. Security Agent                       │
   │  3. Style/Readability Agent              │
   │  4. Test Coverage Agent                  │
   │  5. Documentation Agent                  │
   │  6. Performance Agent                    │
   │  7. Dependency/License Agent             │
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
| Hosting | Streamlit Community Cloud (frontend), Render / Hugging Face Spaces (backend) |

---

## Project Progress

| Day | Focus | Status |
|---|---|---|
| 1 | Environment setup, accounts, folder structure | ✅ Done |
| 2 | GitHub fetcher (diff + old + new code) | ✅ Done |
| 3 | Bug-Hunter Agent (template for all agents) | ⏳ Next |
| 4 | Security, Style, Test Coverage Agents | ⏳ Planned |
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
├── agents/                # specialist agent modules (built Days 3-6)
├── github_fetcher.py      # ✅ pulls PR diff + old/new code via PyGithub
├── graph.py                # LangGraph workflow (built Day 6)
├── app.py                  # Streamlit frontend (built Day 8)
├── requirements.txt
├── .env                     # your secret keys (never committed)
├── .env.example              # safe template of required keys
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
Open `github_fetcher.py`, set `TEST_PR_URL` to any real GitHub PR link, then run:
```bash
python github_fetcher.py
```
This prints a clean summary of every changed file in that PR, including old code, new code, and diff.

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
  Tested successfully across multiple PRs of varying size.

---

## Roadmap / Next Steps

- [ ] Build the 7 specialist agents (Bug-Hunter, Security, Style, Test Coverage, Documentation, Performance, Dependency)
- [ ] Build the Coordinator Agent to merge and prioritize findings
- [ ] Wire everything together with LangGraph
- [ ] Expose the pipeline via a FastAPI `/review` endpoint
- [ ] Build a Streamlit demo UI
- [ ] Stress-test with real PRs and debug using LangSmith traces
- [ ] Deploy and finalize documentation with architecture diagram, screenshots, and live demo link

---

## License

This project is open source and available for anyone to reference or build on. (Add your preferred license here, e.g. MIT.)
