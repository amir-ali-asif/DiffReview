"""
agents/security.py
--------------------
Day 4 module — the Security specialist agent.

Follows the same three-step pattern as Bug-Hunter (Day 3):
    1. Run a real static analysis tool (bandit) on the code.
    2. ALSO run a dedicated, deterministic secret/credential-leak check —
       this does NOT rely on the LLM's judgment, because missing a leaked
       key is exactly the kind of thing that shouldn't depend on a model
       "noticing." Detection here is plain, auditable pattern matching.
    3. Hand both tool outputs to the LLM and ask for a plain-English
       security report, staying strictly in this agent's lane.

Two things this agent checks that go beyond a typical bandit-only setup:
  A. Sensitive FILENAMES committed in the PR (.env, .pem, id_rsa, etc.)
  B. Secret-LOOKING patterns inside the file's content (API keys, AWS
     keys, private key headers, hardcoded passwords) — this runs even
     on non-Python files, since a leaked secret doesn't care what
     language the file is written in. bandit itself only runs on .py
     files, since it's a Python-specific tool.
"""

import os
import re
import subprocess
import tempfile

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()



# ---------------------------------------------------------------------
# Deterministic secret / sensitive-file detection (no LLM involved)
# ---------------------------------------------------------------------

SENSITIVE_FILENAME_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".pypirc", ".npmrc")
SENSITIVE_FILENAME_EXACT = ("id_rsa", "id_rsa.pub", "credentials.json")
SENSITIVE_FILENAME_CONTAINS = ("service-account", "service_account")

# .env files are sensitive UNLESS they're a safe, placeholder-only template.
ENV_FILENAME_PATTERN = re.compile(r"(^|/)\.env(\..+)?$")
ENV_SAFE_EXCEPTIONS = (".env.example", ".env.sample", ".env.template")

SECRET_CONTENT_PATTERNS = {
    "AWS Access Key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Generic API Key / Token": re.compile(
        r"(?i)(api[_-]?key|token)\s*=\s*['\"][A-Za-z0-9_\-]{8,}['\"]"
    ),
    "Private Key Header": re.compile(
        r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "Hardcoded Password": re.compile(r"(?i)password\s*=\s*['\"][^'\"]{4,}['\"]"),
}


def check_sensitive_filename(filename: str):
    """
    Checks if a filename itself is a red flag (e.g. a private key or
    .env file), regardless of what's inside it. Returns a human-readable
    warning string, or None if the filename looks fine.
    """
    base = os.path.basename(filename)

    if ENV_FILENAME_PATTERN.search(filename):
        if not any(base == exc or base.endswith(exc) for exc in ENV_SAFE_EXCEPTIONS):
            return f"Committed environment file detected: '{base}' — this commonly contains live secrets."

    if base.endswith(SENSITIVE_FILENAME_SUFFIXES):
        return f"Committed sensitive file type detected: '{base}' — commonly a private key or credential file."

    if base in SENSITIVE_FILENAME_EXACT:
        return f"Committed known-sensitive filename detected: '{base}'."

    if any(marker in base for marker in SENSITIVE_FILENAME_CONTAINS):
        return f"Committed likely-sensitive filename detected: '{base}'."

    return None


def scan_content_for_secrets(content: str):
    """
    Scans file content for text patterns that look like live secrets.
    Returns a list of human-readable findings (empty list if none found).
    Intentionally simple regex matching, not ML-based — for security
    checks, predictable and auditable beats clever.
    """
    findings = []
    if not content:
        return findings

    for label, pattern in SECRET_CONTENT_PATTERNS.items():
        match = pattern.search(content)
        if match:
            snippet = match.group(0)
            # Truncate/mask so we don't echo a full real secret into logs/reports.
            masked = snippet[:12] + "..." if len(snippet) > 12 else snippet
            findings.append(f"{label} pattern found (e.g. '{masked}')")

    return findings


# ---------------------------------------------------------------------
# bandit integration
# ---------------------------------------------------------------------

def run_bandit(code: str) -> str:
    """Runs bandit on a string of Python code and returns its raw output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["bandit", tmp_path, "-f", "txt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        output = "bandit is not installed or not found in PATH."
    finally:
        os.remove(tmp_path)

    return output if output else "No bandit issues found."


# ---------------------------------------------------------------------
# Prompt + main entry point
# ---------------------------------------------------------------------

def build_prompt(file_context: dict, bandit_output: str, filename_warning, secret_findings: list) -> list:
    system_prompt = (
        "You are the Security agent in an automated code review system. "
        "Your ONLY job is security: vulnerabilities, exposed secrets/credentials, "
        "unsafe queries, unsafe deserialization, and similar risks. Do NOT comment "
        "on style, general bugs, documentation, performance, or test coverage — "
        "other agents handle those.\n\n"
        "If a sensitive file or a leaked secret is flagged below, treat it as "
        "CRITICAL severity and open your report with it. Give a clear, actionable "
        "fix (e.g. 'remove the file with git rm --cached <file>, rotate the "
        "exposed key immediately since it is now in git history, and add the "
        "file to .gitignore').\n\n"
        "For every other finding, explain what the risk is, why it matters, "
        "and how to fix it. Rate each finding as Critical, Major, or Minor. "
        "Also offer brief, non-alarming best-practice suggestions where relevant "
        "(e.g. recommending a secrets manager over hardcoded values). "
        "If nothing is wrong, say so clearly and briefly — do not invent issues."
    )

    filename_section = filename_warning or "No sensitive filename patterns detected."
    secrets_section = "\n".join(f"- {f}" for f in secret_findings) or "No secret-like patterns detected in file content."

    user_prompt = f"""Filename: {file_context['filename']}
Change status: {file_context['status']}

--- SENSITIVE FILENAME CHECK ---
{filename_section}

--- SECRET CONTENT SCAN ---
{secrets_section}

--- NEW CODE / FILE CONTENT ---
{file_context['new_code'] or '(this file was deleted)'}

--- DIFF (changed lines only) ---
{file_context['diff'] or '(no diff available)'}

--- BANDIT OUTPUT ---
{bandit_output}

Based on all of the above, write the Security agent findings report for this file."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_security(file_context: dict) -> dict:
    """
    Main entry point for the Security agent.

    Unlike the other specialist agents, the filename + secret-content
    checks run on EVERY file regardless of language — a leaked key
    doesn't care if the file is Python or not. bandit itself only runs
    when the file is a .py file, since it's a Python-specific tool.
    """
    filename = file_context["filename"]
    code = file_context["new_code"] or ""

    print(f"[Security] Checking filename patterns for {filename}...")
    filename_warning = check_sensitive_filename(filename)

    print("[Security] Scanning content for secret patterns...")
    secret_findings = scan_content_for_secrets(code)

    if filename.endswith(".py"):
        print(f"[Security] Running bandit on {filename}...")
        bandit_output = run_bandit(code)
    else:
        bandit_output = "Skipped — bandit only analyzes Python (.py) files."

    print("[Security] Asking the LLM to interpret the findings...")
    messages = build_prompt(file_context, bandit_output, filename_warning, secret_findings)
    response = invoke_with_fallback(messages)

    return {
        "agent": "security",
        "filename": filename,
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

    print(f"Fetching PR: {test_pr_url}")
    contexts = fetch_pr_context(test_pr_url)
    python_files, skipped_files = filter_python_files(contexts)

    if not python_files:
        raise SystemExit("No Python files found in this PR to test the agent on.")

    first_file = python_files[0]
    result = run_security(first_file)

    print("\n" + "=" * 60)
    print("SECURITY REPORT")
    print("=" * 60)
    print(f"File: {result['filename']}\n")
    print(result["report"])
    print("=" * 60)