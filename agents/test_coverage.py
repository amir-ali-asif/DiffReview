"""
agents/test_coverage.py
-------------------------
Day 4 module — the Test Coverage specialist agent.

IMPORTANT SCOPE NOTE (read this first):
True, repo-wide test coverage requires the full repository checked out
with its existing test suite installed and runnable. Since this pipeline
works off individual changed files (see github_fetcher.py, Day 2), tests
for a given source file usually live in a SEPARATE file this agent can't
see. Rather than pretending to run the project's real test suite, this
agent uses a deliberately scoped, honest approach:

  1. AST heuristic: parse the new code and list every top-level function
     that is NOT itself a test function (doesn't start with "test_"),
     then check whether any test function IN THE SAME FILE appears to
     reference it. This catches the common "this new function has zero
     visible tests in this file" case.

  2. Self-contained coverage run: treat the file itself as a mini test
     suite (source + any test_ functions inside it) and run it through
     pytest + coverage.py. This produces a REAL, genuine percentage when
     a file contains both source and tests together.

  3. The LLM combines both signals to reason about whether the change
     looks adequately tested, calling out specific untested functions or
     missing edge cases — while being explicitly told to phrase findings
     as "no tests visible in this file" rather than claiming certainty
     that no tests exist anywhere in the project.

This is a documented, intentional limitation, not a hidden gap — and a
good "Future Work" callout: a more complete version would check out the
full PR branch and run the project's real test suite against just the
changed lines.
"""

import ast
import os
import subprocess
import tempfile

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()



def find_untested_functions(code: str):
    """
    Parses the code with Python's ast module and returns a list of
    top-level function names that have no apparent test function
    referencing them within the same file.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    all_functions = [
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ]
    source_functions = [name for name in all_functions if not name.startswith("test_")]

    test_functions_code = "\n".join(
        (ast.get_source_segment(code, node) or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )

    untested = [name for name in source_functions if name not in test_functions_code]
    return untested


def run_self_contained_coverage(code: str) -> str:
    """
    Runs the file itself through pytest + coverage.py, treating any
    test_ functions inside it as the test suite. Returns the raw
    coverage report text, or an explanatory message if there's nothing
    to run — which is common and expected on real PRs where tests live
    in a separate file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, "module_under_test.py")
        with open(tmp_path, "w") as f:
            f.write(code)

        try:
            subprocess.run(
                ["coverage", "run", "--source", tmp_dir, "-m", "pytest", tmp_path, "-q"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmp_dir,
            )
            report = subprocess.run(
                ["coverage", "report", "-m"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmp_dir,
            )
            output = report.stdout.strip()
        except FileNotFoundError:
            output = "coverage/pytest is not installed or not found in PATH."

    return output if output else "No test functions found in this file to measure coverage against."


def build_prompt(file_context: dict, untested_functions: list, coverage_output: str) -> list:
    system_prompt = (
        "You are the Test Coverage agent in an automated code review system. "
        "Your ONLY job is assessing whether the changed code has adequate "
        "tests. Do NOT comment on style, security, documentation, performance, "
        "or general logic bugs — other agents handle those.\n\n"
        "You are working with LIMITED visibility: you can only see this one "
        "file, not the project's full test suite (tests often live in "
        "separate files you cannot see). Use the heuristic list of functions "
        "with no visible in-file tests, and the coverage tool output, as "
        "SIGNALS, not absolute proof. Phrase findings appropriately, e.g. "
        "'No tests for this function are visible in this file; if tests exist "
        "elsewhere in the project, disregard this' rather than stating with "
        "certainty that no tests exist anywhere.\n\n"
        "For genuinely thin or missing test coverage, explain what's untested "
        "and what edge cases (empty input, zero, negative numbers, None, etc.) "
        "seem unaddressed. Rate each finding as Major or Minor. If coverage "
        "looks adequate, say so clearly and briefly — do not invent gaps."
    )

    untested_section = (
        ", ".join(untested_functions)
        if untested_functions
        else "None — all functions appear to have an in-file test reference."
    )

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- NEW CODE ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- FUNCTIONS WITH NO VISIBLE IN-FILE TEST REFERENCE ---
{untested_section}

--- SELF-CONTAINED COVERAGE.PY OUTPUT ---
{coverage_output}

Based on all of the above, write the Test Coverage agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_test_coverage(file_context: dict) -> dict:
    code = file_context["new_code"] or ""

    print(f"[Test Coverage] Checking for untested functions in {file_context['filename']}...")
    untested_functions = find_untested_functions(code)

    print("[Test Coverage] Running self-contained coverage check...")
    coverage_output = run_self_contained_coverage(code)

    print("[Test Coverage] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, untested_functions, coverage_output)
    response = invoke_with_fallback(messages)

    return {
        "agent": "test_coverage",
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
    result = run_test_coverage(first_file)

    print("\n" + "=" * 60)
    print("TEST COVERAGE REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)