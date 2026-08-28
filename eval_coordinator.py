"""
eval_coordinator.py
---------------------
Day 6 addition — a small, standalone evaluation harness for the
Coordinator agent specifically.

WHY THIS IS SEPARATE FROM eval_runner.py:
eval_runner.py (Days 3-5) grades the 7 specialist agents on two things:
recall (did it catch a known issue in CODE?) and false positives. The
Coordinator doesn't analyze code at all — its input is a list of
ALREADY-WRITTEN mock agent reports, and its job is reasoning ABOUT those
reports (merging duplicates, ordering by severity, writing a summary).
That's a fundamentally different shape of test, so it gets its own
small script rather than being forced into the generic per-file
fixture loader.

WHAT THIS CHECKS (four distinct properties, one per fixture case):
  1. dedup            — same issue described by 2+ agents becomes ONE
                         finding in the final report, not duplicated.
  2. severity_order    — Critical findings appear before Major, which
                         appear before Minor, regardless of input order.
  3. no_hallucination   — when every input report says "no issues",
                         the final verdict doesn't invent problems.
  4. skipped_files_note  — skipped (non-Python) files are mentioned as
                         a transparency note, not treated as a finding.

HOW TO RUN:
    python eval_coordinator.py
"""

import os
import json

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from agents.coordinator import run_coordinator

load_dotenv()

judge_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_fixtures", "coordinator")


def ask_judge(question: str) -> bool:
    """Sends a strict yes/no question to the judge LLM and returns True/False."""
    system_prompt = (
        "You are a strict grading judge. Answer with exactly one word: "
        "YES or NO. No explanation."
    )
    response = judge_llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=question)]
    )
    return response.content.strip().upper().startswith("YES")


def check_dedup(final_report: str, case: dict) -> tuple:
    """Checks that the duplicate-described issue appears as ONE finding, not two."""
    topic = case["duplicate_topic"]
    question = f"""Here is a code review verdict:

{final_report}

Question: Does this verdict mention the following issue as ONE single, merged
finding — NOT as two separate, duplicated bullet points or entries?
Issue: {topic}

Answer YES if it's merged into one finding. Answer NO if it appears twice/duplicated."""
    passed = ask_judge(question)
    return passed, f"Issue '{topic}' merged into a single finding: {'YES' if passed else 'NO'}"


def check_severity_order(final_report: str, case: dict) -> tuple:
    """Checks that Critical findings are presented before Major, before Minor."""
    question = f"""Here is a code review verdict:

{final_report}

Question: In this verdict, are findings presented in this order: all CRITICAL
findings first, then all MAJOR findings, then all MINOR findings — regardless
of what order they might have been reported in originally?

Answer YES if the ordering is correct (Critical before Major before Minor).
Answer NO if a lower-severity finding is presented before a higher-severity one."""
    passed = ask_judge(question)
    return passed, f"Severity ordering (Critical > Major > Minor) correct: {'YES' if passed else 'NO'}"


def check_no_hallucination(final_report: str, case: dict) -> tuple:
    """Checks that no findings were invented when all inputs said 'no issues'."""
    question = f"""Here is a code review verdict, written after every specialist
agent reported NO issues found:

{final_report}

Question: Does this verdict incorrectly invent or claim to have found real
bugs, vulnerabilities, or issues, even though none were actually reported by
any specialist agent?

Answer YES if it incorrectly invented issues. Answer NO if it correctly says
the code looks fine / recommends approval without inventing problems."""
    hallucinated = ask_judge(question)
    passed = not hallucinated
    return passed, f"No hallucinated findings on clean input: {'YES' if passed else 'NO (hallucinated)'}"


def check_skipped_files_note(final_report: str, case: dict) -> tuple:
    """Checks that skipped files are mentioned as a note, not as a finding/issue."""
    skipped = ", ".join(case["skipped_filenames"])
    question = f"""Here is a code review verdict:

{final_report}

Question: Does this verdict mention the following skipped files ({skipped}) as
a plain, low-key TRANSPARENCY NOTE (e.g. "not reviewed by Python-specific
agents") WITHOUT treating them as a bug, vulnerability, or severity-rated
finding?

Answer YES if handled correctly as a transparency note only.
Answer NO if the skipped files are missing entirely, OR if they were
incorrectly treated as an actual finding/issue."""
    passed = ask_judge(question)
    return passed, f"Skipped files handled as a transparency note: {'YES' if passed else 'NO'}"


CHECK_FUNCTIONS = {
    "dedup": check_dedup,
    "severity_order": check_severity_order,
    "no_hallucination": check_no_hallucination,
    "skipped_files_note": check_skipped_files_note,
}


def load_cases():
    cases = []
    for fname in sorted(os.listdir(FIXTURES_DIR)):
        if fname.endswith("_input.json"):
            with open(os.path.join(FIXTURES_DIR, fname)) as f:
                case = json.load(f)
            case["case_id"] = fname.replace("_input.json", "")
            cases.append(case)
    return cases


def run_eval():
    cases = load_cases()
    results = []

    print("=" * 60)
    print("EVALUATING: Coordinator Agent")
    print("=" * 60)

    for case in cases:
        case_id = case["case_id"]
        check_type = case["check_type"]
        print(f"\n--- {case_id} ({check_type}): {case['description'][:80]} ---")

        result = run_coordinator(case["agent_reports"], case.get("skipped_filenames", []))
        final_report = result["report"]

        check_fn = CHECK_FUNCTIONS[check_type]
        passed, message = check_fn(final_report, case)

        icon = "✅" if passed else "❌"
        print(f"  {icon} {message}")

        results.append({"case_id": case_id, "check_type": check_type, "passed": passed})

    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    print(f"\n{'-' * 60}")
    print(f"SCORECARD — coordinator")
    print(f"{'-' * 60}")
    print(f"Checks passed: {passed_count}/{total}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['case_id']} — {r['check_type']}")
    print(f"{'-' * 60}")

    return results


if __name__ == "__main__":
    run_eval()
