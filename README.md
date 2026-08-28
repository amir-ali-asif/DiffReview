# Multi-Agent System for Automated Code Review

> A multi-agent AI system that replicates a full engineering review team, giving solo developers and small startups the same level of code review rigor that only large companies with dedicated departments can normally afford.

**Status:** 🚧 In active development — Day 6 of 10 complete. Full pipeline runs end-to-end on real PRs.

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

## How It Works (Full Pipeline — Now Running End-to-End)

```
GitHub PR Link (input)
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
   │  (each = static analysis tool + LLM,     │
   │   all traced live in LangSmith)          │
   │                                            │
   │  *Security also scans ALL changed files   │
   │   (any language) for secrets/keys         │
   │  †Dependency only runs on manifest files   │
   │   (requirements.txt, Pipfile, etc.)        │
   └────────────────┬─────────────────────────┘
                     ↓
              Coordinator Agent                  ✅ built + evaluated (Day 6)
   (merges findings, resolves conflicts/duplicates,
    prioritizes issues, notes skipped files,
    writes final verdict)
                     ↓
         Final Report (FastAPI + Streamlit)       ⏳ planned (Days 7-8)
         + Full reasoning trace in LangSmith
```

**LangGraph orchestration (`graph.py`), built Day 6:** wires everything above into a single "fan-out, fan-in" graph — `fetch` feeds all 7 specialist nodes, which run in parallel, and all 7 feed into `coordinator`, which only runs once every specialist has finished. Each specialist node internally loops over every relevant changed file, so one graph node still reviews an entire PR's worth of files. `python graph.py` now runs the complete pipeline, start to finish, on a real PR link.

Each specialist agent combines the output of a **real static analysis tool** with **LLM reasoning** to explain findings in plain, human-readable language — this isn't "just prompting an LLM," it's real tooling plus AI interpretation, similar to how production tools like CodeRabbit and Sourcery work.

### The 7 Specialist Agents + Coordinator, at a Glance

| # | Agent | Paired Tool | Notable design decision |
|---|---|---|---|
| 1 | Bug-Hunter | `pylint` + `flake8` | Template agent — the tool→LLM pattern every other agent reuses |
| 2 | Security | `bandit` + custom secret scanner | Deterministic (non-LLM) detection for leaked credentials — too important to leave to model judgment |
| 3 | Style/Readability | `pylint` (convention/refactor only) + `black --check` | Scoped tool flags to avoid duplicating Bug-Hunter's findings |
| 4 | Test Coverage | `ast` heuristic + self-contained `pytest`/`coverage.py` | Honest scope limitation: can't see tests in separate files |
| 5 | Documentation | Custom `ast`-based docstring analysis | Only agent with no external CLI tool — checks both missing AND low-quality docstrings |
| 6 | Performance | `radon` (complexity + maintainability) | LLM explicitly told to reason beyond radon's structural score |
| 7 | Dependency/License | `pip-audit` | Only agent scoped to manifest files; also flags unpinned dependencies |
| — | **Coordinator** | — (pure LLM reasoning) | **Deduplicates overlapping findings, prioritizes by real severity, writes one final verdict** |

### Coordinator Agent — Merging 7 Reports Into One Verdict

Unlike the specialist agents, the Coordinator runs no static analysis tool at all — its input is the 7 agents' already-written reports, and its job is three things an LLM is genuinely well-suited for:

1. **Deduplicate** — if two agents describe the same underlying issue in different words (e.g. Security calling something a "SQL injection vulnerability" while Bug-Hunter calls the same code "will throw unexpected errors"), merge them into ONE finding.
2. **Prioritize** — order everything by real severity (Critical > Major > Minor), with agent type as a tiebreaker: Security > Bug-Hunter > Test Coverage > Performance > Dependency > Style > Documentation.
3. **Write the final verdict** — a one-line summary, a clear recommendation (approve / request changes / block merge), then the deduplicated, prioritized findings, plus a transparency note on any files skipped by the Python-only agents.

### Security Agent — Secret & Credential Protection

Beyond pairing with `bandit` for vulnerable code patterns, the Security agent includes a dedicated, **deterministic** check (not left to LLM judgment) that:

- Flags known-risky filenames committed in the PR — `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, `service-account*.json`, etc. (`.env.example` is allowed)
- Scans file contents/diffs for patterns that look like live secrets — AWS access keys, generic API key/token assignments, private key headers, hardcoded passwords
- When something is found, the report is specific and actionable, e.g.: *"🚨 `.env` appears to have been committed — this likely contains live secrets. Remove it with `git rm --cached .env`, rotate any exposed keys immediately, and confirm `.env` is in `.gitignore`."*

---

## Automated Evaluation Framework

Rather than only testing agents by hand, this project includes **two complementary fixture-based evaluation harnesses:**

### `eval_runner.py` — for the 7 specialist agents

- Each agent has a library of test cases under `test_fixtures/<agent_name>/` — deliberately buggy/vulnerable code paired with a hand-written "expected findings" JSON file.
- Fixtures generally follow a 3-case pattern: an **obvious** issue, a **subtle** issue (stress-tests whether the agent goes beyond what its paired tool flags outright), and a **clean-code control case** (tests for false positives). Security gets a 4th case for the leaked-`.env`-file scenario.
- Grading uses **LLM-as-judge**: a separate, strict grading LLM call checks whether each expected finding is actually covered by the agent's report.
- **Reliability checking (`--runs`):** since LLMs aren't perfectly deterministic even at `temperature=0`, each fixture case can be run multiple times (`python eval_runner.py bug_hunter --runs 3`), scored on majority vote, with any disagreement between runs flagged as **flaky**. Default is 1 run for fast iteration; `--runs 3`+ is for when a score needs to hold up statistically, not just anecdotally.
- `python eval_runner.py` with no argument runs **all 7 agents** in one command.

**Fixture coverage (7 agents, 22 cases):**

| Agent | Cases | What's tested |
|---|---|---|
| Bug-Hunter | 3 | Empty-list crash, mutable default argument, clean code control |
| Security | 4 | SQL injection, hardcoded API key, leaked `.env` file, secure code control |
| Style | 3 | Bad naming/formatting, deep nesting, clean PEP8 control |
| Test Coverage | 3 | No tests, incomplete edge-case tests, fully tested control |
| Documentation | 3 | Missing docstrings, thin/low-value docstrings, well-documented control |
| Performance | 3 | O(n²) nested loop, string-concat-in-loop, efficient code control |
| Dependency | 3 | Known-vulnerable pinned package, unpinned dependencies, safely pinned control |

### `eval_coordinator.py` — for the Coordinator, added Day 6

The Coordinator's job is fundamentally different (reasoning about pre-written reports, not analyzing code), so it gets its own small, purpose-built harness rather than being forced into `eval_runner.py`'s per-file fixture shape. Fixtures live under `test_fixtures/coordinator/` as mock-report JSON files, and each is graded on a different property:

| Case | Property tested |
|---|---|
| `case_01` (dedup) | Two agents describing the same issue differently get merged into ONE finding |
| `case_02` (severity_order) | Findings fed in the wrong order get correctly re-sorted Critical → Major → Minor |
| `case_03` (no_hallucination) | When every input says "no issues," the verdict doesn't invent problems |
| `case_04` (skipped_files_note) | Skipped files are mentioned as a transparency note, not treated as a finding |

Run with `python eval_coordinator.py`.

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
| Evaluation | Two custom fixture-based harnesses (LLM-as-judge, with multi-run reliability checking for specialist agents) |
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
| 5 | Documentation, Performance, Dependency Agents — all 7 agents complete | ✅ Done |
| 6 | Coordinator Agent + LangGraph orchestration — first end-to-end run | ✅ Done |
| 7 | FastAPI backend | ⏳ Next |
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
│   └── coordinator/                           # ✅ 4 mock-report cases (dedup, ordering, etc.)
├── eval_runner.py                                # ✅ evaluates all 7 specialist agents (supports --runs)
├── eval_coordinator.py                            # ✅ evaluates the Coordinator's reasoning properties
├── github_fetcher.py                               # ✅ pulls PR diff + old/new code via PyGithub
├── graph.py                                          # ✅ LangGraph pipeline — fetch → 7 agents → coordinator
├── app.py                                              # Streamlit frontend (built Day 8)
├── requirements.txt
├── .env                                                 # your secret keys (never committed)
├── .env.example                                           # safe template of required keys
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
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (classic, `repo` scope) — needed to fetch PR data

### 5. Verify the setup
```bash
python hello_world.py
```

### 6. Run the full pipeline end-to-end
Set `TEST_PR_URL` in your `.env` to any real PR link, then:
```bash
python graph.py
```
This runs all 7 specialist agents plus the Coordinator and prints one final, consolidated report — the entire system, start to finish, in one command.

### 7. Test the Coordinator on its own (faster, no PR needed)
```bash
python agents/coordinator.py
```
Runs a built-in mock scenario that checks whether overlapping findings get correctly merged.

### 8. Run the automated evaluation suites
```bash
python eval_runner.py                     # all 7 specialist agents
python eval_runner.py security --runs 3    # one agent, reliability check
python eval_coordinator.py                 # the Coordinator's reasoning properties
```

---

## What's Working So Far

- ✅ Full local dev environment with Groq + Gemini + LangSmith wired up and verified
- ✅ `github_fetcher.py` — returns a structured `file_context` object per changed file; `filter_python_files()` now returns full file contexts for skipped files too (Day 6 update), enabling Security and Dependency to act on non-Python files
- ✅ **All 7 specialist agents built and evaluated** — see the agent table above
- ✅ **Coordinator agent** — deduplicates, prioritizes by severity, and writes one final verdict from all 7 agents' reports
- ✅ **`graph.py`** — the complete pipeline wired together with LangGraph in a fan-out/fan-in pattern; runs end-to-end on a real PR link
- ✅ **Two evaluation harnesses** — `eval_runner.py` (22 fixture cases across the 7 specialist agents, with multi-run reliability checking) and `eval_coordinator.py` (4 mock-report cases checking dedup, severity ordering, hallucination-resistance, and skipped-file handling)

---

## Roadmap / Next Steps

- [ ] Expose the pipeline via a FastAPI `/review` endpoint, with error handling for invalid PR links, GitHub rate limits, and LLM provider failures
- [ ] Build a Streamlit demo UI
- [ ] Stress-test with real PRs and debug using LangSmith traces
- [ ] Add a second, whole-pipeline evaluation layer using LangSmith Evaluations (complementing the two fixture harnesses with real-PR, end-to-end testing)
- [ ] Deploy and finalize documentation with architecture diagram, screenshots, and live demo link
- [ ] **Future work:** multi-language support (ESLint for JS/TS, Semgrep for cross-language security scanning)
- [ ] **Future work:** sequential agent communication (agents referencing each other's findings)

---

## License

This project is open source and available for anyone to reference or build on.