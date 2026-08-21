"""
eval_runner.py
---------------
Automated evaluation harness for the specialist agents.

WHY THIS EXISTS:
Manually eyeballing agent output doesn't scale, and doesn't give you a
number to point to ("this agent catches 90% of known bugs"). This script
automates that: it runs each agent against a library of fixture code
files with KNOWN, pre-documented issues, then uses a second LLM call
("LLM-as-judge") to check whether the agent's report actually covers
each expected finding. It also checks for false positives on clean code.

RELIABILITY / CONSISTENCY CHECKING:
LLMs are not perfectly deterministic, even at temperature=0 — the same
prompt can occasionally produce a different answer on different runs.
A recall score based on running each fixture ONCE tells you what
happened that one time, not how reliable the agent actually is. This
script supports running each fixture case multiple times (--runs N) and
reports, for every expected finding, what FRACTION of runs caught it —
plus flags any case where runs disagreed with each other ("flaky").
Default is --runs 1 for fast day-to-day iteration; use --runs 3 or more
before trusting a score enough to put it in a README or report.

HOW FIXTURES ARE ORGANIZED:
    test_fixtures/
    └── <agent_name>/
        ├── case_01_something.py       <- code with a known issue (or none)
        ├── case_01_expected.json      <- {"description": "...", "bugs": [...]}
        ├── case_02_something.py
        ├── case_02_expected.json
        ...

The "bugs" key name is generic on purpose — for the Security agent later
you'd write {"vulnerabilities": [...]}, for Dependency you'd write
{"issues": [...]}, etc. This script reads whatever list is inside the
JSON regardless of the key name, so no framework changes are needed when
new agents are added.

HOW TO ADD A NEW AGENT TO THIS FRAMEWORK:
    1. Create test_fixtures/<agent_name>/ with case files + expected.json
    2. Import that agent's run_ function at the top of this file
    3. Add one line to AGENT_REGISTRY at the bottom

HOW TO RUN:
    python eval_runner.py bug_hunter              (1 run per case, fast)
    python eval_runner.py bug_hunter --runs 3      (3 runs per case, reliable)
    python eval_runner.py --runs 3                 (all agents, 3 runs each)
    python eval_runner.py                          (all agents, 1 run each)
"""

import os
import re
import sys
import json

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

FIXTURES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_fixtures")

# A separate, cheap, low-temperature model call used ONLY to grade reports.
# Kept separate from the agents' own LLM calls so grading logic stays in
# one place and doesn't get mixed into agent prompts.
judge_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0)


# ---------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------

def load_fixture_cases(agent_name: str):
    """
    Finds every case_XX pair (code file + expected.json) inside
    test_fixtures/<agent_name>/ and returns them as a list of dicts:
        {
            "case_id": "case_01",
            "code_path": "...",
            "code": "...",
            "expected_items": ["...", "..."],   # may be empty list
            "description": "..."
        }
    """
    agent_dir = os.path.join(FIXTURES_ROOT, agent_name)
    if not os.path.isdir(agent_dir):
        raise SystemExit(f"No fixtures folder found at: {agent_dir}")

    cases = {}
    for fname in sorted(os.listdir(agent_dir)):
        match = re.match(r"(case_\d+)_", fname)
        if not match:
            continue
        case_id = match.group(1)
        cases.setdefault(case_id, {})

        if fname.endswith(".json"):
            with open(os.path.join(agent_dir, fname)) as f:
                data = json.load(f)
            cases[case_id]["description"] = data.get("description", "")
            # Grab whatever list is inside the JSON, regardless of key name
            # (bugs / vulnerabilities / issues / etc.)
            list_values = [v for v in data.values() if isinstance(v, list)]
            cases[case_id]["expected_items"] = list_values[0] if list_values else []
        else:
            code_path = os.path.join(agent_dir, fname)
            with open(code_path) as f:
                cases[case_id]["code"] = f.read()
            cases[case_id]["code_path"] = code_path
            cases[case_id]["case_id"] = case_id

    return [cases[cid] for cid in sorted(cases.keys())]


def code_to_file_context(code: str, filename: str) -> dict:
    """
    Fixtures are standalone code snippets, not real PRs, so we wrap them
    in the same file_context shape every agent expects — with old_code
    and diff set to None since there's no "before" version here.
    """
    return {
        "filename": filename,
        "old_code": None,
        "new_code": code,
        "diff": None,
        "status": "added",
    }


# ---------------------------------------------------------------------
# LLM-as-judge grading
# ---------------------------------------------------------------------

def judge_finding_covered(report_text: str, expected_finding: str) -> bool:
    """
    Asks a separate LLM call: "does this agent report actually mention
    this specific known issue?" Returns True/False.

    Why an LLM judge instead of simple string matching: the agent writes
    natural language ("this crashes with ZeroDivisionError on an empty
    list...") which will never exactly match a short expected description
    ("Division by zero on empty list"). A judge model can recognize that
    these describe the same issue even with completely different wording.
    """
    system_prompt = (
        "You are a strict grading judge. You will be given an agent's "
        "code review report and one specific issue that SHOULD be "
        "mentioned in it. Answer with exactly one word: YES if the "
        "report clearly identifies this issue (even with different "
        "wording), or NO if it does not."
    )
    user_prompt = f"""AGENT REPORT:
{report_text}

EXPECTED ISSUE:
{expected_finding}

Does the report identify this issue? Answer YES or NO only."""

    response = judge_llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    return response.content.strip().upper().startswith("YES")


def judge_false_positive(report_text: str) -> bool:
    """
    For CLEAN code fixtures (expected_items == []), asks: did the agent
    claim to find real problems anyway? Returns True if it hallucinated
    an issue (a false positive), False if it correctly reported no bugs.
    """
    system_prompt = (
        "You are a strict grading judge. You will be given an agent's "
        "code review report written about CODE THAT IS ALREADY CORRECT "
        "with no real bugs. Answer with exactly one word: YES if the "
        "report incorrectly claims to have found real bugs/issues, or "
        "NO if it correctly reports that no real issues were found."
    )
    user_prompt = f"""AGENT REPORT:
{report_text}

Does this report incorrectly claim to have found real bugs? Answer YES or NO only."""

    response = judge_llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    return response.content.strip().upper().startswith("YES")


# ---------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------

def evaluate_agent(agent_name: str, run_agent_fn, runs: int = 1):
    """
    Runs every fixture case for one agent, grades the results, and
    prints + returns a scorecard.

    Each case is run `runs` times (not just once). For every expected
    finding, we compute what FRACTION of those runs caught it — a
    finding only counts as reliably "caught" if the majority of runs
    caught it, and we separately track "flaky" checks where runs
    disagreed with each other. This distinguishes "this agent reliably
    catches this bug" from "this agent got lucky once."
    """
    print(f"\n{'=' * 60}")
    print(f"EVALUATING AGENT: {agent_name}  (runs per case: {runs})")
    print("=" * 60)

    cases = load_fixture_cases(agent_name)
    total_expected = 0
    total_caught = 0          # majority-vote catches
    false_positives = 0       # majority-vote false positives
    flaky_checks = []         # checks where runs disagreed with each other
    case_results = []

    for case in cases:
        case_id = case["case_id"]
        print(f"\n--- {case_id}: {case.get('description', '')[:80]} ---")

        file_context = code_to_file_context(case["code"], case["code_path"])

        # Run the agent `runs` times on the SAME input, collecting each
        # report separately — this is what lets us measure consistency.
        reports = []
        for run_number in range(1, runs + 1):
            if runs > 1:
                print(f"    (run {run_number}/{runs})")
            result = run_agent_fn(file_context)
            reports.append(result["report"])

        expected_items = case["expected_items"]

        if not expected_items:
            # Clean-code control case — check for false positives on EACH run.
            fp_flags = [judge_false_positive(r) for r in reports]
            fp_rate = sum(fp_flags) / len(fp_flags)
            is_flaky = 0 < fp_rate < 1
            majority_fp = fp_rate >= 0.5

            if majority_fp:
                false_positives += 1

            status = "⚠️  FALSE POSITIVE" if majority_fp else "✅ Correctly found no issues"
            consistency_note = f" (INCONSISTENT: {sum(fp_flags)}/{len(fp_flags)} runs flagged it)" if is_flaky else ""
            print(f"  {status} on clean code{consistency_note}")

            if is_flaky:
                flaky_checks.append(f"{case_id}: false-positive check")

            case_results.append({
                "case_id": case_id,
                "false_positive": majority_fp,
                "false_positive_rate": round(fp_rate, 2),
                "flaky": is_flaky,
            })
        else:
            caught_here = 0
            for item in expected_items:
                total_expected += 1
                covered_flags = [judge_finding_covered(r, item) for r in reports]
                coverage_rate = sum(covered_flags) / len(covered_flags)
                is_flaky = 0 < coverage_rate < 1
                majority_caught = coverage_rate >= 0.5

                if majority_caught:
                    caught_here += 1
                    total_caught += 1

                icon = "✅" if majority_caught else "❌"
                consistency_note = (
                    f" (INCONSISTENT: caught in {sum(covered_flags)}/{len(covered_flags)} runs)"
                    if is_flaky else ""
                )
                print(f"  {icon} {'Caught' if majority_caught else 'Missed'}: {item}{consistency_note}")

                if is_flaky:
                    flaky_checks.append(f"{case_id}: {item}")

            case_results.append({
                "case_id": case_id,
                "expected": len(expected_items),
                "caught": caught_here,
            })

    recall = (total_caught / total_expected * 100) if total_expected else 100.0
    total_checks = total_expected + len([c for c in cases if not c["expected_items"]])
    consistency_percent = (
        (total_checks - len(flaky_checks)) / total_checks * 100 if total_checks else 100.0
    )

    print(f"\n{'-' * 60}")
    print(f"SCORECARD — {agent_name}  (runs per case: {runs})")
    print(f"{'-' * 60}")
    print(f"Known issues caught:   {total_caught}/{total_expected}  ({recall:.0f}% recall)")
    print(f"False positives:       {false_positives} (on clean-code control cases)")
    if runs > 1:
        print(f"Consistency:           {consistency_percent:.0f}% of checks were unanimous across {runs} runs")
        if flaky_checks:
            print(f"Flaky checks:           {len(flaky_checks)}")
            for fc in flaky_checks:
                print(f"    - {fc}")
    print(f"{'-' * 60}")

    return {
        "agent": agent_name,
        "runs_per_case": runs,
        "recall_percent": round(recall, 1),
        "caught": total_caught,
        "expected": total_expected,
        "false_positives": false_positives,
        "consistency_percent": round(consistency_percent, 1),
        "flaky_checks": flaky_checks,
        "case_results": case_results,
    }


if __name__ == "__main__":
    # Add the project root to the path so agent imports work.
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(project_root)

    from agents.bug_hunter import run_bug_hunter

    # --- AGENT_REGISTRY ---
    # All 7 specialist agents are now registered — Day 5 completes the set.
    AGENT_REGISTRY = {
        "bug_hunter": run_bug_hunter
    }

    requested = None
    runs = 1
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--runs":
            runs = int(args[i + 1])
            i += 2
        else:
            requested = args[i]
            i += 1

    agents_to_run = [requested] if requested else list(AGENT_REGISTRY.keys())

    all_results = []
    for agent_name in agents_to_run:
        if agent_name not in AGENT_REGISTRY:
            print(f"Unknown agent: {agent_name}. Registered agents: {list(AGENT_REGISTRY.keys())}")
            continue
        result = evaluate_agent(agent_name, AGENT_REGISTRY[agent_name], runs=runs)
        all_results.append(result)

    # Save results so scores can be tracked over time.
    os.makedirs("eval_results", exist_ok=True)
    output_path = os.path.join("eval_results", "latest_results.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nFull results saved to {output_path}")