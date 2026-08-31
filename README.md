# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 8 of 10 complete. Full working demo: paste a PR link, get a live AI-generated review in the browser.

---

## Problem Statement

In large, professional companies, code review is handled by separate specialized departments — QA/testing, security, code quality/standards, plus roles covering test coverage, documentation, performance, and dependency management.

Small startups and solo developers don't have this luxury. One person (or a tiny team) has to handle all of it alone, which leads to rushed or skipped reviews, bugs and security issues slipping into production, declining code quality over time, and bottlenecks when only one senior developer is available.

This project solves that by building an AI system that acts as a full, always-available review team — instantly reviewing GitHub Pull Requests with the rigor of a large company's multiple departments, without needing to hire more people.

---

## Scope & Limitations

**This project currently reviews Python (`.py`) code only.**

Every static analysis tool used by the specialist agents — `pylint`, `flake8`, `bandit`, `coverage.py`, `black`, `radon`, `pip-audit`, and the `ast`-based documentation check — is Python-specific. A PR that changes non-Python files will still be fetched in full, but only `.py` files are sent to the language-specific specialist agents for review. Non-Python files are explicitly filtered out and tracked (not silently dropped), so the Coordinator's final report always lists what was and wasn't reviewed.

**Two deliberate, documented exceptions to the Python-only filter:**
- The **Security agent's** secret/credential-leak check runs on **every file, regardless of language** — a leaked API key or a committed `.env` file doesn't care what language the surrounding project is written in.
- The **Dependency agent** only makes sense on dependency manifest files (`requirements.txt`, `Pipfile`, `pyproject.toml`) — none of which are `.py` files either.

**One more honest, documented limitation:** the Test Coverage agent can only see the single changed file it's given, not the project's full test suite (which usually lives in separate files). It's scoped to reason about what's visible in-file, phrased with appropriate humility rather than false certainty.

Multi-language support (e.g. ESLint for JS/TS) is a planned Future Work item, not part of the current build.

---

## How It Works (Full Pipeline — Now Running End-to-End, With a Live UI)

```
                              ┌─────────────────────────┐
                              │   Streamlit Frontend      │  ✅ Day 8
                              │   (paste PR link, click   │
                              │    "Run Review")          │
                              └────────────┬─────────────┘
                                           │ HTTP POST /review
                                           ↓
                              ┌─────────────────────────┐
                              │   FastAPI Backend          │  ✅ Day 7
                              │   (error handling, Groq→   │
                              │    Gemini fallback)        │
                              └────────────┬─────────────┘
                                           ↓
PyGithub fetches diff + old code + new code   ✅ built (Day 2)
        ↓
Filter: Python files → agents | non-Python → skipped list   ✅ built (Day 6)
        ↓
   ┌────────────────────────────────────────┐
   │   7 Specialist Agents (parallel)         │  ✅ ALL BUILT + EVALUATED
   │  1. Bug-Hunter Agent                     │  ✅ Day 3
   │  2. Security Agent*                      │  ✅ Day 4
   │  3. Style/Readability Agent              │  ✅ Day 4
   │  4. Test Coverage Agent                  │  ✅ Day 4
   │  5. Documentation Agent                  │  ✅ Day 5
   │  6. Performance Agent                    │  ✅ Day 5
   │  7. Dependency/License Agent†             │  ✅ Day 5
   └────────────────┬─────────────────────────┘
                     ↓
              Coordinator Agent                  ✅ built + evaluated (Day 6)
                     ↓
         Final Report → back to Streamlit UI       ✅ Day 8
         + Full reasoning trace in LangSmith
```

*Security also scans ALL changed files (any language) for secrets/keys. †Dependency only runs on manifest files (requirements.txt, Pipfile, etc.)

Each specialist agent combines the output of a **real static analysis tool** with **LLM reasoning** to explain findings in plain, human-readable language — this isn't "just prompting an LLM," it's real tooling plus AI interpretation, similar to how production tools like CodeRabbit and Sourcery work.

### The 7 Specialist Agents + Coordinator, at a Glance

| # | Agent | Paired Tool | Notable design decision |
|---|---|---|---|
| 1 | Bug-Hunter | `pylint` + `flake8` | Template agent — the tool→LLM pattern every other agent reuses |
| 2 | Security | `bandit` + custom secret scanner | Deterministic (non-LLM) detection for leaked credentials |
| 3 | Style/Readability | `pylint` (convention/refactor only) + `black --check` | Scoped tool flags to avoid duplicating Bug-Hunter's findings |
| 4 | Test Coverage | `ast` heuristic + self-contained `pytest`/`coverage.py` | Honest scope limitation: can't see tests in separate files |
| 5 | Documentation | Custom `ast`-based docstring analysis | Only agent with no external CLI tool |
| 6 | Performance | `radon` (complexity + maintainability) | LLM explicitly told to reason beyond radon's structural score |
| 7 | Dependency/License | `pip-audit` | Only agent scoped to manifest files |
| — | **Coordinator** | — (pure LLM reasoning) | Deduplicates overlapping findings, prioritizes by real severity, writes one final verdict |

### Coordinator Agent — Merging 7 Reports Into One Verdict

The Coordinator runs no static analysis tool — its input is the 7 agents' already-written reports, and it: (1) **deduplicates** overlapping findings described in different words, (2) **prioritizes** by real severity (Critical > Major > Minor, with Security > Bug-Hunter > Test Coverage > Performance > Dependency > Style > Documentation as a tiebreaker), and (3) **writes a final verdict** — a one-line summary, a merge recommendation, the deduplicated findings, and a transparency note on any skipped files.

### Security Agent — Secret & Credential Protection

Beyond pairing with `bandit`, the Security agent includes a dedicated, **deterministic** check (not left to LLM judgment) that flags known-risky filenames (`.env`, `*.pem`, `id_rsa`, etc.) and scans content for secret-like patterns (API keys, AWS keys, private key headers, hardcoded passwords). Findings are specific and actionable, e.g.: *"🚨 `.env` appears to have been committed — remove it with `git rm --cached .env`, rotate any exposed keys, and confirm `.env` is in `.gitignore`."*

### Reliability: Automatic Groq → Gemini Fallback

Every agent's LLM calls go through a shared `llm_client.py` module instead of calling Groq directly. If Groq fails for *any* reason — rate limit, outage, or a deprecated model (which genuinely happened mid-build: `llama-3.3-70b-versatile` was decommissioned by Groq on August 16, 2026) — the exact same request is automatically retried against Gemini, with zero code changes needed in any of the 8 agent files that use it. This was a deliberate architectural payoff: because every agent followed the same `llm.invoke(...)` pattern from Day 3 onward, adding this fallback was one mechanical 3-line change repeated 8 times, not 8 different bespoke fixes.

### FastAPI Backend — `/review` Endpoint

`main.py` exposes the full pipeline as a single `POST /review` endpoint (interactive docs at `/docs`), with error handling mapped to real HTTP status codes:

| Failure | Status | Cause |
|---|---|---|
| Malformed PR URL | `400` | Doesn't match `github.com/.../pull/N` |
| PR or repo not found | `404` | Invalid owner/repo/PR number |
| GitHub rate limit hit | `429` | Too many requests to GitHub's API |
| Both Groq and Gemini fail | `502` | Total LLM provider outage |

### Streamlit Frontend — the Live Demo

`app.py` is the interface recruiters and interviewers will actually click through: paste a PR link, click **Run Review**, watch a loading spinner while all 7 agents + the Coordinator run, then see a color-coded final verdict (red/yellow/green by severity) followed by 7 expandable sections — one per agent, each showing per-file findings with a lightweight severity badge. The frontend talks to the backend purely over HTTP (`requests.post(...)`), never importing the agents directly — this decoupling is what makes independent deployment of frontend and backend (Day 10) possible.

---

## Automated Evaluation Framework

Rather than only testing agents by hand, this project includes **two complementary fixture-based evaluation harnesses:**

### `eval_runner.py` — for the 7 specialist agents

- Each agent has a library of test cases under `test_fixtures/<agent_name>/`: an **obvious** issue, a **subtle** issue, and a **clean-code control case** (Security gets a 4th, for the leaked-`.env` scenario).
- Grading uses **LLM-as-judge** — a separate strict grading call checks whether each expected finding is actually covered by the agent's report.
- **Reliability checking:** `python eval_runner.py <agent> --runs 3` runs each case multiple times, scores on majority vote, and flags any case where runs disagreed as **flaky** — because a single-run score doesn't account for LLM non-determinism.
- `python eval_runner.py` with no argument runs **all 7 agents** in one command (22 total fixture cases).

### `eval_coordinator.py` — for the Coordinator

A separate, purpose-built harness since the Coordinator's input (pre-written mock reports, not code) and the properties worth checking (dedup, ordering, honesty) are fundamentally different from the specialist agents' recall/false-positive grading:

| Case | Property tested |
|---|---|
| `case_01` (dedup) | Two agents describing the same issue differently get merged into ONE finding |
| `case_02` (severity_order) | Findings fed in the wrong order get correctly re-sorted Critical → Major → Minor |
| `case_03` (no_hallucination) | When every input says "no issues," the verdict doesn't invent problems |
| `case_04` (skipped_files_note) | Skipped files are mentioned as a transparency note, not treated as a finding |

---

## Tech Stack (100% Free Tools)

| Layer | Tool |
|---|---|
| Agent Orchestration | LangGraph |
| LLM | Groq API (`openai/gpt-oss-120b`), with automatic Gemini (`gemini-2.5-flash`) fallback |
| Code Parsing | Python `ast` module |
| PR Fetching | PyGithub |
| Static Analysis | `pylint`, `flake8`, `bandit`, `coverage.py`, `black`, `pytest`, `radon`, `pip-audit` |
| Backend | FastAPI |
| Frontend | Streamlit |
| Observability | LangSmith |
| Evaluation | Two custom fixture-based harnesses (LLM-as-judge, with multi-run reliability checking) |
| Hosting | Streamlit Community Cloud (frontend), Render / Hugging Face Spaces (backend) |

---

## Project Progress

| Day | Focus | Status |
|---|---|---|
| 1 | Environment setup, accounts, folder structure | ✅ Done |
| 2 | GitHub fetcher (diff + old + new code) | ✅ Done |
| 3 | Bug-Hunter Agent + automated evaluation framework | ✅ Done |
| 4 | Security, Style, Test Coverage Agents | ✅ Done |
| 5 | Documentation, Performance, Dependency Agents — all 7 agents complete | ✅ Done |
| 6 | Coordinator Agent + LangGraph orchestration — first end-to-end run | ✅ Done |
| 7 | FastAPI backend + Groq→Gemini fallback | ✅ Done |
| 8 | Streamlit frontend — full working demo | ✅ Done |
| 9 | Testing, debugging via LangSmith | ⏳ Next |
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
│   ├── test_coverage.py            # ✅ ast heuristic + self-contained coverage.py + LLM
│   ├── documentation.py             # ✅ custom ast-based docstring analysis + LLM
│   ├── performance.py                # ✅ radon (complexity + maintainability) + LLM
│   ├── dependency.py                  # ✅ pip-audit + LLM (manifest files only)
│   └── coordinator.py                  # ✅ merges/dedupes/prioritizes all 7 reports
├── test_fixtures/
│   ├── bug_hunter/                     # ✅ 3 fixture cases
│   ├── security/                        # ✅ 4 fixture cases (incl. leaked .env)
│   ├── style/                            # ✅ 3 fixture cases
│   ├── test_coverage/                     # ✅ 3 fixture cases
│   ├── documentation/                      # ✅ 3 fixture cases
│   ├── performance/                         # ✅ 3 fixture cases
│   ├── dependency/                           # ✅ 3 fixture cases
│   └── coordinator/                           # ✅ 4 mock-report cases
├── llm_client.py                                 # ✅ shared Groq→Gemini fallback wrapper
├── eval_runner.py                                 # ✅ evaluates all 7 specialist agents (supports --runs)
├── eval_coordinator.py                             # ✅ evaluates the Coordinator's reasoning properties
├── github_fetcher.py                                # ✅ pulls PR diff + old/new code via PyGithub
├── graph.py                                           # ✅ LangGraph pipeline — fetch → 7 agents → coordinator
├── main.py                                              # ✅ FastAPI backend (/review endpoint)
├── app.py                                                 # ✅ Streamlit frontend
├── requirements.txt
├── .env                                                     # your secret keys (never committed)
├── .env.example                                               # safe template of required keys
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
```bash
cp .env.example .env
```

You'll need free API keys from:
- [Groq](https://console.groq.com) — primary LLM
- [Google AI Studio](https://aistudio.google.com) — Gemini fallback LLM
- [LangSmith](https://smith.langchain.com) — tracing/observability
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (classic, `repo` scope)

### 5. Verify the setup
```bash
python hello_world.py
```

### 6. Run the full pipeline from the command line (no UI)
```bash
python graph.py
```

### 7. Run the live demo (recommended way to try it)

**Terminal 1 — start the backend:**
```bash
uvicorn main:app --reload
```

**Terminal 2 — start the frontend:**
```bash
streamlit run app.py
```

Then open the Streamlit tab that pops up (usually `http://localhost:8501`), paste a real PR link, and click **Run Review**.

### 8. Run the automated evaluation suites
```bash
python eval_runner.py                     # all 7 specialist agents
python eval_runner.py security --runs 3    # one agent, reliability check
python eval_coordinator.py                 # the Coordinator's reasoning properties
```

---

## What's Working So Far

- ✅ Full local dev environment with Groq + Gemini + LangSmith wired up and verified
- ✅ **All 7 specialist agents + the Coordinator**, built and evaluated
- ✅ **`graph.py`** — the complete pipeline wired together with LangGraph in a fan-out/fan-in pattern
- ✅ **Automatic Groq → Gemini fallback** (`llm_client.py`) across every agent, with a real deprecation event already survived during the build
- ✅ **FastAPI backend** (`main.py`) — a working `/review` endpoint with mapped error handling for invalid URLs, missing PRs, rate limits, and total LLM failure
- ✅ **Streamlit frontend** (`app.py`) — a full, working, end-to-end demo: paste a link, click a button, get a color-coded verdict and 7 expandable per-agent reports in the browser
- ✅ **Two evaluation harnesses** — `eval_runner.py` (22 fixture cases, multi-run reliability checking) and `eval_coordinator.py` (4 mock-report cases)

---

## Roadmap / Next Steps

- [ ] Run the full pipeline on 5-6 different real PRs and use LangSmith traces to find and fix weak spots
- [ ] Handle edge cases: empty PRs, documentation-only PRs, very large PRs (rate limit handling)
- [ ] Write up a concrete "caught and fixed this using LangSmith" debugging story for the README/portfolio
- [ ] Add a whole-pipeline evaluation layer using LangSmith Evaluations, complementing the two fixture harnesses with real-PR, end-to-end testing
- [ ] Deploy backend (Render/HF Spaces) and frontend (Streamlit Community Cloud); confirm the live deployed app works end-to-end
- [ ] Finalize documentation: architecture diagram, screenshots/GIF of the app, link to live demo
- [ ] **Future work:** multi-language support (ESLint for JS/TS, Semgrep for cross-language security scanning)
- [ ] **Future work:** sequential agent communication (agents referencing each other's findings)
- [ ] **Future work:** full-repository checkout for genuinely accurate test coverage analysis (vs. today's single-file visibility)

---

## License

This project is open source and available for anyone to reference or build on.