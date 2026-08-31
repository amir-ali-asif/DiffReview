"""
agents/dependency.py
-----------------------
Day 5 module — the Dependency/License specialist agent, and the last of
the 7 specialist agents.

Unlike the other 6 agents, this one only makes sense on DEPENDENCY
MANIFEST files (requirements.txt, Pipfile, pyproject.toml, etc.) — it
doesn't analyze arbitrary source code. It pairs with pip-audit, which
checks pinned package versions against known vulnerability databases.

IMPORTANT — a design note carried into Day 6:
Dependency manifest files are NOT .py files, so the Day 2 Python-only
filter (filter_python_files) routes them into the "skipped" list, same
as any other non-Python file. This means graph.py (Day 6) needs one
more small routing rule: any skipped file that IS a dependency manifest
should still be sent to THIS agent, even though it was filtered out of
the 6 Python-only agents. This mirrors the Security agent's earlier
exception (its secret scan also needs to see non-Python files).

Note: pip-audit needs internet access to check current vulnerability
data (it queries PyPI's vulnerability feed), so this agent's results
can genuinely change over time as new CVEs get disclosed — which is
exactly why re-running the eval suite periodically is valuable, not
just once at initial build time.
"""

import os
import subprocess
import tempfile

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()



def is_dependency_file(filename: str) -> bool:
    """
    Checks whether a filename is a recognized dependency manifest.
    Only these files make sense to run through pip-audit.
    """
    base = os.path.basename(filename).lower()
    if base in ("pipfile", "pipfile.lock", "pyproject.toml"):
        return True
    if "requirements" in base and base.endswith(".txt"):
        return True
    return False


def run_pip_audit(requirements_content: str) -> str:
    """
    Runs pip-audit against a requirements.txt-style file and returns its
    raw output. Requires internet access to check live vulnerability data.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(requirements_content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["pip-audit", "-r", tmp_path, "--desc"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout or result.stderr).strip()
    except FileNotFoundError:
        output = "pip-audit is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No dependency vulnerabilities found."


def build_prompt(file_context: dict, pip_audit_output: str) -> list:
    system_prompt = (
        "You are the Dependency/License agent in an automated code review "
        "system. Your ONLY job is outdated or vulnerable dependencies (and "
        "risky version-pinning practices). Do NOT comment on application "
        "logic, style, documentation, or test coverage — other agents "
        "handle those.\n\n"
        "For each vulnerable package pip-audit reports, explain the risk in "
        "plain English and state the safe version to upgrade to. ALSO "
        "specifically flag dependencies with NO version pin at all, or an "
        "overly broad range (e.g. 'requests' with no version, or '>=1.0'), "
        "even if pip-audit doesn't report anything concrete for them — "
        "unpinned dependencies are a real risk because they can silently "
        "resolve to a vulnerable version later, even if today's resolution "
        "happens to be safe. Rate each finding as Critical, Major, or Minor. "
        "If everything looks safely pinned and free of known vulnerabilities, "
        "say so clearly and briefly — do not invent issues."
    )

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- FILE CONTENT ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- PIP-AUDIT OUTPUT ---
{pip_audit_output}

Based on all of the above, write the Dependency/License agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_dependency(file_context: dict) -> dict:
    filename = file_context["filename"]
    content = file_context["new_code"] or ""

    if not is_dependency_file(filename):
        return {
            "agent": "dependency",
            "filename": filename,
            "report": (
                f"Skipped — '{filename}' is not a recognized dependency "
                "manifest file (expected requirements*.txt, Pipfile, "
                "Pipfile.lock, or pyproject.toml)."
            ),
        }

    print(f"[Dependency] Running pip-audit on {filename}...")
    pip_audit_output = run_pip_audit(content)

    print("[Dependency] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, pip_audit_output)
    response = invoke_with_fallback(messages)

    return {
        "agent": "dependency",
        "filename": filename,
        "report": response.content,
    }


if __name__ == "__main__":
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(project_root)

    from github_fetcher import fetch_pr_context

    test_pr_url = os.getenv("TEST_PR_URL")
    if not test_pr_url:
        raise SystemExit(
            "Missing TEST_PR_URL in your .env file.\n"
            "Add a line like:\n"
            "  TEST_PR_URL=https://github.com/owner/repo/pull/1"
        )

    # Note: this test block deliberately does NOT use filter_python_files,
    # since dependency manifests are never .py files and would otherwise
    # be filtered out entirely.
    contexts = fetch_pr_context(test_pr_url)
    dependency_files = [fc for fc in contexts if is_dependency_file(fc["filename"])]

    if not dependency_files:
        raise SystemExit(
            "No dependency manifest files (requirements.txt, Pipfile, etc.) "
            "found in this PR. Try a PR that changes requirements.txt, or "
            "test with 'python eval_runner.py dependency' instead."
        )

    first_file = dependency_files[0]
    result = run_dependency(first_file)

    print("\n" + "=" * 60)
    print("DEPENDENCY REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)