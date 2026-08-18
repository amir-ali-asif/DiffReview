"""
agents/bug_hunter.py
---------------------
Day 3 module — the first specialist agent, and the TEMPLATE for all
the other 6 specialist agents built on Days 4-5.

The pattern every specialist agent follows is always the same:
    1. Run a real static analysis tool on the code, capture its output.
    2. Hand that tool output + the code (old/new/diff) to the LLM.
    3. Ask the LLM to turn the raw tool output into a clear, plain-English
       findings report, staying strictly within this agent's lane.

What THIS agent specifically does:
- Runs pylint AND flake8 on the new version of the code
- Focuses only on logic errors, runtime issues, and broken functionality
- Does NOT comment on style, security, docs, performance, etc. — those
  are other agents' jobs

Because LANGCHAIN_TRACING_V2=true is set in your .env (from Day 1), every
call to the LLM here is automatically traced and viewable in LangSmith —
you'll see the exact prompt sent and the exact response received.
"""

import os
import subprocess
import tempfile

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

# One shared LLM connection for this agent.
# temperature=0 keeps findings consistent/repeatable rather than creative.
llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0)


def run_pylint(code: str) -> str:
    """
    Runs pylint on a string of Python code and returns its raw output.

    Why we write the code to a temporary file first: pylint is a
    command-line tool built to analyze real files on disk — it can't
    scan a Python string directly. We create a throwaway temp file,
    run pylint against it, capture the output, then delete the temp file.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["pylint", tmp_path, "--disable=all", "--enable=E,W,C,R", "--score=n"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "pylint is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No pylint issues found."


def run_flake8(code: str) -> str:
    """Same idea as run_pylint, but for flake8."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["flake8", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "flake8 is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No flake8 issues found."


def build_prompt(file_context: dict, pylint_output: str, flake8_output: str) -> list:
    """
    Builds the exact messages sent to the LLM.

    We give the model FOUR things:
      1. A system prompt that tells it exactly what its job is (and isn't)
      2. The old code (before the PR)
      3. The new code (after the PR)
      4. The raw tool output from pylint + flake8

    Why include old_code and diff, not just new_code: a bug is often only
    visible when you understand what CHANGED, not just what the final
    code looks like in isolation.
    """
    system_prompt = (
        "You are the Bug-Hunter agent in an automated code review system. "
        "Your ONLY job is to find logic errors, runtime issues, and broken "
        "functionality. Do NOT comment on style, formatting, security, "
        "documentation, performance, or test coverage — other agents "
        "handle those areas. Stay strictly in your lane.\n\n"
        "For each real bug you find, explain in plain English:\n"
        "1. What the bug is\n"
        "2. Why it's a problem (what could go wrong at runtime)\n"
        "3. A suggested fix\n\n"
        "Rate each bug's severity as Critical, Major, or Minor.\n"
        "If you find no real bugs, say so clearly and briefly — do not "
        "invent issues just to appear thorough."
    )

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- OLD CODE ---
{file_context['old_code'] or '(this is a new file, no old version exists)'}

--- NEW CODE ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- PYLINT OUTPUT ---
{pylint_output}

--- FLAKE8 OUTPUT ---
{flake8_output}

Based on all of the above, write the Bug-Hunter findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_bug_hunter(file_context: dict) -> dict:
    """
    Main entry point for this agent — this is the function every other
    part of the system (and eventually graph.py) will call.

    Input:  one file_context dictionary (from github_fetcher.py)
    Output: {
        "agent": "bug_hunter",
        "filename": "...",
        "report": "<plain-English findings written by the LLM>"
    }
    """
    code_to_check = file_context["new_code"] or ""

    print(f"[Bug-Hunter] Running pylint on {file_context['filename']}...")
    pylint_output = run_pylint(code_to_check)

    print(f"[Bug-Hunter] Running flake8 on {file_context['filename']}...")
    flake8_output = run_flake8(code_to_check)

    print("[Bug-Hunter] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, pylint_output, flake8_output)
    response = llm.invoke(messages)

    return {
        "agent": "bug_hunter",
        "filename": file_context["filename"],
        "report": response.content,
    }


if __name__ == "__main__":
    # This block lets you test this agent directly with:
    #     python agents/bug_hunter.py
    # It reuses github_fetcher.py from Day 2 to pull a real PR, then runs
    # this agent on the first Python file it finds.

    import sys

    # Add the project root to the import path so "from github_fetcher import ..."
    # works no matter where this script is run from.
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

    print(f"Fetching PR: {test_pr_url}")
    contexts = fetch_pr_context(test_pr_url)
    python_files, skipped_files = filter_python_files(contexts)

    if not python_files:
        raise SystemExit("No Python files found in this PR to test the agent on.")

    print(f"Found {len(python_files)} Python file(s). Testing Bug-Hunter on the first one...\n")

    first_file = python_files[0]
    result = run_bug_hunter(first_file)

    print("\n" + "=" * 60)
    print("BUG-HUNTER REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)