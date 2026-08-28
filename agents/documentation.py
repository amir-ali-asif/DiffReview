"""
agents/documentation.py
-------------------------
Day 5 module — the Documentation specialist agent.

Unlike the other agents, this one is NOT paired with an external CLI
tool — it's paired with a custom check built directly on Python's
built-in `ast` module, per the original project spec. The ast module
parses the code's structure so we can programmatically find every
function/class and check whether it has a docstring, without needing
any third-party linter.

Two checks run before the LLM sees anything:
  1. Functions/classes with NO docstring at all (the obvious case).
  2. Functions/classes with a docstring that exists but looks too thin
     to be useful (very short, or just restates the name) — the LLM
     still makes the final call here, but the heuristic flags candidates
     so the LLM doesn't have to read every single docstring itself.
"""

import ast
import os

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


MIN_USEFUL_DOCSTRING_LENGTH = 15  # characters


def analyze_docstrings(code: str) -> dict:
    """
    Parses the code and returns:
        {
            "missing": ["func_or_class_name", ...],
            "thin": ["func_or_class_name", ...],
        }
    "missing" = no docstring at all.
    "thin" = has a docstring, but it's very short (likely low-value,
             e.g. "TODO" or just repeating the function name).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"missing": [], "thin": []}

    missing = []
    thin = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Skip private/dunder helpers and test functions — not the
            # primary target of documentation review.
            if node.name.startswith("_") or node.name.startswith("test_"):
                continue

            docstring = ast.get_docstring(node)
            if docstring is None:
                missing.append(node.name)
            elif len(docstring.strip()) < MIN_USEFUL_DOCSTRING_LENGTH:
                thin.append(node.name)

    return {"missing": missing, "thin": thin}


def build_prompt(file_context: dict, analysis: dict) -> list:
    system_prompt = (
        "You are the Documentation agent in an automated code review system. "
        "Your ONLY job is missing or inadequate docstrings/comments. Do NOT "
        "comment on logic bugs, security, style/formatting, performance, or "
        "test coverage — other agents handle those.\n\n"
        "For each function or class missing a docstring, or with a docstring "
        "too thin to be useful, explain what it does (based on reading the "
        "code) and suggest a clear docstring including purpose, parameters, "
        "and return value where relevant. Rate each as Major (public/complex "
        "function with zero documentation) or Minor (simple function, or a "
        "docstring that's just a bit thin). If documentation looks adequate, "
        "say so clearly and briefly — do not invent issues."
    )

    missing_section = ", ".join(analysis["missing"]) or "None"
    thin_section = ", ".join(analysis["thin"]) or "None"

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- NEW CODE ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- FUNCTIONS/CLASSES WITH NO DOCSTRING ---
{missing_section}

--- FUNCTIONS/CLASSES WITH A SUSPICIOUSLY THIN DOCSTRING ---
{thin_section}

Based on all of the above, write the Documentation agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_documentation(file_context: dict) -> dict:
    code = file_context["new_code"] or ""

    print(f"[Documentation] Analyzing docstrings in {file_context['filename']}...")
    analysis = analyze_docstrings(code)

    print("[Documentation] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, analysis)
    response = invoke_with_fallback(messages)

    return {
        "agent": "documentation",
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
    result = run_documentation(first_file)

    print("\n" + "=" * 60)
    print("DOCUMENTATION REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)
