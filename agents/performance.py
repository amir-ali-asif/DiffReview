"""
agents/performance.py
------------------------
Day 5 module — the Performance specialist agent.

Follows the same pattern as the other agents:
    1. Run radon (cyclomatic complexity + maintainability index) on the code.
    2. Hand the tool output + code to the LLM.
    3. Ask for a plain-English performance/efficiency report.

radon measures STRUCTURAL complexity (how tangled the control flow is),
which correlates with maintenance risk but doesn't catch every real
performance problem — e.g. an O(n^2) algorithm written as simple,
un-nested-looking code can still be structurally "simple" by radon's
metric while being genuinely slow. That's why the LLM is given the full
code too, not just radon's numbers, and is explicitly asked to reason
about algorithmic efficiency directly.
"""

import os
import subprocess
import tempfile

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()



def run_radon_complexity(code: str) -> str:
    """Runs radon's cyclomatic complexity (cc) check and returns raw output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["radon", "cc", tmp_path, "-s"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "radon is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No complexity data returned."


def run_radon_maintainability(code: str) -> str:
    """Runs radon's maintainability index (mi) check and returns raw output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["radon", "mi", tmp_path, "-s"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "radon is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No maintainability data returned."


def build_prompt(file_context: dict, cc_output: str, mi_output: str) -> list:
    system_prompt = (
        "You are the Performance agent in an automated code review system. "
        "Your ONLY job is inefficient code, unnecessary complexity, and "
        "algorithmic performance concerns. Do NOT comment on logic bugs "
        "(unless the inefficiency IS the bug), security, style, documentation, "
        "or test coverage — other agents handle those.\n\n"
        "Use the radon complexity/maintainability numbers as a starting "
        "signal, but reason about the ACTUAL algorithm yourself too — radon "
        "measures structural complexity, not algorithmic efficiency, so a "
        "simple-looking loop can still hide an O(n^2) or worse problem "
        "(e.g. repeated linear scans, string concatenation in a loop, "
        "redundant recomputation). For each real issue, explain what's "
        "inefficient, roughly why (e.g. 'O(n^2) due to a linear search "
        "inside a loop'), and a concrete fix. Rate each as Major or Minor. "
        "If performance looks fine, say so clearly and briefly — do not "
        "invent issues."
    )

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- NEW CODE ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- RADON CYCLOMATIC COMPLEXITY OUTPUT ---
{cc_output}

--- RADON MAINTAINABILITY INDEX OUTPUT ---
{mi_output}

Based on all of the above, write the Performance agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_performance(file_context: dict) -> dict:
    code = file_context["new_code"] or ""

    print(f"[Performance] Running radon complexity check on {file_context['filename']}...")
    cc_output = run_radon_complexity(code)

    print(f"[Performance] Running radon maintainability check on {file_context['filename']}...")
    mi_output = run_radon_maintainability(code)

    print("[Performance] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, cc_output, mi_output)
    response = invoke_with_fallback(messages)

    return {
        "agent": "performance",
        "filename": file_context["filename"],
        "report": response.content,
    }


if __name__ == "__main__":
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(project_root)

    from github_fetcher import fetch_pr_context, filter_python_files

    test_pr_url = os.getenv("TEST_PR_URL")
    if not test_pr_url:
        raise SystemExit(
            "Missing TEST_PR_URL in your .env file.\n"
            "Add a line like:\n"
            "  TEST_PR_URL=https://github.com/owner/repo/pull/1"
        )

    contexts = fetch_pr_context(test_pr_url)
    python_files, skipped_files = filter_python_files(contexts)

    if not python_files:
        raise SystemExit("No Python files found in this PR to test the agent on.")

    first_file = python_files[0]
    result = run_performance(first_file)

    print("\n" + "=" * 60)
    print("PERFORMANCE REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)
