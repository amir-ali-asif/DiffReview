"""
agents/style.py
-----------------
Day 4 module — the Style/Readability specialist agent.

Follows the same pattern as Bug-Hunter:
    1. Run pylint (convention + refactor checks ONLY) and black --check.
    2. Hand the tool output + code to the LLM.
    3. Ask for a plain-English style/readability report.

Note on overlap between agents: pylint's full output can overlap with
what Bug-Hunter (Day 3) already reports, since pylint mixes error/
warning/convention/refactor codes together. This agent intentionally
only enables the "C" (convention) and "R" (refactor) categories, keeping
it scoped to style/readability specifically. Any remaining overlap in
what different agents notice is expected and is handled later by the
Coordinator agent (Day 6), whose specific job is to deduplicate findings
across all 7 specialist reports — it's not something we need to solve
perfectly at the individual agent level.
"""

import os
import subprocess
import tempfile

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

def run_pylint_style(code: str) -> str:
    """Runs pylint with ONLY convention (C) and refactor (R) checks enabled."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["pylint", tmp_path, "--disable=all", "--enable=C,R", "--score=n"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "pylint is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No pylint style issues found."


def run_black_check(code: str) -> str:
    """
    Runs black in --check --diff mode, which does NOT modify the file —
    it only reports what it WOULD change to match standard formatting.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["black", "--check", "--diff", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "black is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No formatting changes needed (black is satisfied)."


def build_prompt(file_context: dict, pylint_output: str, black_output: str) -> list:
    system_prompt = (
        "You are the Style/Readability agent in an automated code review system. "
        "Your ONLY job is naming conventions, formatting, and clean-code "
        "readability. Do NOT comment on logic bugs, security, documentation "
        "completeness, performance, or test coverage — other agents handle those.\n\n"
        "For each real style issue you find, explain in plain English what it "
        "is, why it hurts readability/maintainability, and how to fix it. Rate "
        "each as Major (meaningfully hurts readability) or Minor (nitpick/polish).\n\n"
        "If you find no real issues, say so clearly and briefly — do not invent "
        "issues just to appear thorough."
    )

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- NEW CODE ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- PYLINT (convention + refactor only) OUTPUT ---
{pylint_output}

--- BLACK --check OUTPUT ---
{black_output}

Based on all of the above, write the Style/Readability agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_style(file_context: dict) -> dict:
    code = file_context["new_code"] or ""

    print(f"[Style] Running pylint (style checks) on {file_context['filename']}...")
    pylint_output = run_pylint_style(code)

    print(f"[Style] Running black --check on {file_context['filename']}...")
    black_output = run_black_check(code)

    print("[Style] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, pylint_output, black_output)
    response = llm.invoke(messages)

    return {
        "agent": "style",
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
    result = run_style(first_file)

    print("\n" + "=" * 60)
    print("STYLE REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)