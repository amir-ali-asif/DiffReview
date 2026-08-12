# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 2 of 10 complete.

---

## Problem Statement

In large, professional companies, code review is handled by separate specialized departments — QA/testing, security, code quality/standards, plus roles covering test coverage, documentation, performance, and dependency management.

Small startups and solo developers don't have this luxury. One person (or a tiny team) has to handle all of it alone, which leads to rushed or skipped reviews, bugs and security issues slipping into production, declining code quality over time, and bottlenecks when only one senior developer is available.

This project solves that by building an AI system that acts as a full, always-available review team — instantly reviewing GitHub Pull Requests with the rigor of a large company's multiple departments, without needing to hire more people.

---

## Scope & Limitations

**This project currently reviews Python (`.py`) code only.**

Every static analysis tool in the stack — `pylint`, `flake8`, `bandit`, `coverage.py`, `radon`, `pip-audit`, and the `ast`-based documentation check — is Python-specific. A PR that changes non-Python files (JavaScript, Java, config files, etc.) will still be fetched in full, but only the `.py` files are sent to the 6 language-specific specialist agents for review.

- Non-Python files are **not silently dropped** — they're explicitly filtered out and listed in the final Coordinator report (e.g. *"3 files skipped (not Python): App.tsx, style.css, README.md"*) so the developer always knows what was and wasn't reviewed.
- **One exception:** the Security Agent's secret/credential-leak check (see below) runs on **every changed file regardless of language**, since a leaked API key or private key file can appear in any file type, not just Python.
- Multi-language support (e.g. ESLint for JS/TS, Semgrep for cross-language security scanning) is a natural next step and is listed under Future Work.

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
   │     7 Specialist Agents (parallel)       │  🚧 in progress (Days 3-5)
   │  1. Bug-Hunter Agent                     │
   │  2. Security Agent*                      │
   │  3. Style/Readability Agent              │
   │  4. Test Coverage Agent                  │
   │  5. Documentation Agent                  │
   │  6. Performance Agent                    │
   │  7. Dependency/License Agent             │
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

Beyond pairing with `bandit` for vulnerable code patterns, the Security Agent includes a dedicated, deterministic check (not left to LLM judgment) that:

- Flags known-risky filenames committed in the PR — `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, `service-account*.json`, etc. (`.env.example` is allowed)
- Scans file contents/diffs for patterns that look like live secrets — AWS access keys, generic API key/token assignments, private key headers, hardcoded passwords
- When something is found, the report is specific and actionable, e.g.: *"🚨 `.env` appears to have been committed — this likely contains live secrets. Remove it with `git rm --cached .env`, rotate any exposed keys immediately, and confirm `.env` is in `.gitignore`."*
- Also offers lighter-touch, non-alarming recommendations (e.g. missing `.gitignore` entries, suggesting a secrets manager over hardcoded values)

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
- ✅ `filter_python_files()` — splits fetched files into Python files (sent to agents) vs. non-Python files (skipped, but still tracked and reported)

---

## Roadmap / Next Steps

- [ ] Build the 7 specialist agents (Bug-Hunter, Security, Style, Test Coverage, Documentation, Performance, Dependency)
- [ ] Wire the Python-file filter and skipped-file tracking into `graph.py`
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