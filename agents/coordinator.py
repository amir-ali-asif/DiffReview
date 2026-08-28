"""
agents/coordinator.py
------------------------
Day 6 module — the Coordinator agent, the final piece that turns 7
separate specialist reports into ONE clean, prioritized verdict for
the whole PR.

Unlike the specialist agents, the Coordinator doesn't run any static
analysis tool — its whole job is reading everyone else's reports and
doing three things an LLM is genuinely well-suited for:
    1. DEDUPLICATE — different agents sometimes flag the same underlying
       issue in different words (e.g. Bug-Hunter and Security both
       noticing an unvalidated input). Merge these into one finding.
    2. PRIORITIZE — order findings by real severity (Critical > Major >
       Minor), using agent type as a tiebreaker: Security > Bug-Hunter >
       Test Coverage > Performance > Dependency > Style > Documentation.
    3. VERDICT — write one clear summary + a merge recommendation
       (e.g. "1 critical security issue, 2 bugs, 3 minor style issues.
       Recommendation: fix critical issues before merging.")
"""

import os

from dotenv import load_dotenv
from llm_client import invoke_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


AGENT_PRIORITY_ORDER = [
    "security",
    "bug_hunter",
    "test_coverage",
    "performance",
    "dependency",
    "style",
    "documentation",
]


def format_reports_for_prompt(agent_reports: list) -> str:
    """
    Groups the flat list of {"agent", "filename", "report"} dicts by
    filename, then orders each file's reports by agent priority, so the
    LLM reads a clean, organized block instead of a jumbled list.
    """
    by_filename = {}
    for r in agent_reports:
        by_filename.setdefault(r["filename"], []).append(r)

    sections = []
    for filename, reports in by_filename.items():
        reports_sorted = sorted(
            reports,
            key=lambda r: AGENT_PRIORITY_ORDER.index(r["agent"])
            if r["agent"] in AGENT_PRIORITY_ORDER else 99,
        )
        block = [f"### File: {filename}"]
        for r in reports_sorted:
            block.append(f"\n--- {r['agent'].upper()} AGENT REPORT ---\n{r['report']}")
        sections.append("\n".join(block))

    return "\n\n".join(sections) if sections else "No specialist reports were generated."


def build_prompt(agent_reports: list, skipped_filenames: list) -> list:
    system_prompt = (
        "You are the Coordinator agent in an automated code review system. "
        "You have received findings reports from up to 7 specialist agents "
        "(Bug-Hunter, Security, Style, Test Coverage, Documentation, "
        "Performance, Dependency), each covering one narrow area of review "
        "for the same Pull Request.\n\n"
        "Your job:\n"
        "1. DEDUPLICATE — if two agents describe the same underlying issue "
        "in different words, merge them into ONE finding, don't list it "
        "twice. Note which agents raised it.\n"
        "2. PRIORITIZE — order all findings by real severity: Critical "
        "first, then Major, then Minor. Within the same severity, "
        "prioritize in this order: Security > Bug-Hunter > Test Coverage "
        "> Performance > Dependency > Style > Documentation.\n"
        "3. WRITE A FINAL VERDICT — start with a one-line summary (e.g. "
        "'1 critical security issue, 2 bugs, 3 minor style issues.'), a "
        "clear recommendation (approve / request changes / block merge), "
        "then the deduplicated, prioritized list of findings grouped by "
        "severity, each attributed to which agent(s) raised it.\n\n"
        "If a list of skipped (non-Python) files is provided, mention them "
        "briefly at the end as 'not reviewed by the Python-specific agents' "
        "— do not treat this as a finding or issue, just a transparency note."
    )

    reports_section = format_reports_for_prompt(agent_reports)
    skipped_section = ", ".join(skipped_filenames) if skipped_filenames else "None"

    user_prompt = f"""SPECIALIST AGENT REPORTS:

{reports_section}

--- FILES NOT REVIEWED BY PYTHON-SPECIFIC AGENTS ---
{skipped_section}

Write the final Coordinator verdict for this Pull Request."""

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def run_coordinator(agent_reports: list, skipped_filenames: list = None) -> dict:
    """
    Main entry point for the Coordinator.

    Input:
        agent_reports: flat list of {"agent", "filename", "report"} dicts
                        from all specialist agents, across all files.
        skipped_filenames: filenames that were fetched but not reviewed
                        by the Python-specific agents.
    Output:
        {"agent": "coordinator", "report": "<final verdict>"}
    """
    skipped_filenames = skipped_filenames or []

    print(f"[Coordinator] Merging {len(agent_reports)} specialist reports...")
    messages = build_prompt(agent_reports, skipped_filenames)
    response = invoke_with_fallback(messages)

    return {
        "agent": "coordinator",
        "report": response.content,
    }


if __name__ == "__main__":
    # A small standalone test using hand-written mock reports — lets you
    # verify dedup + prioritization behavior WITHOUT running the full
    # pipeline first. For a real end-to-end run, use graph.py instead.
    #
    # This mock deliberately has Security and Bug-Hunter both flagging
    # the SAME underlying SQL injection issue in different words — a
    # correct Coordinator should merge these into one finding, not list
    # it twice.
    mock_reports = [
        {
            "agent": "security",
            "filename": "auth.py",
            "report": "CRITICAL: SQL injection vulnerability in login() due to unsanitized string concatenation in the query. Fix: use parameterized queries.",
        },
        {
            "agent": "bug_hunter",
            "filename": "auth.py",
            "report": "MAJOR: login() builds a SQL query by concatenating user input directly, which can also cause unexpected query errors on special characters, not just a security risk.",
        },
        {
            "agent": "style",
            "filename": "auth.py",
            "report": "MINOR: function name 'login' could be more descriptive, e.g. 'authenticate_user'.",
        },
    ]

    result = run_coordinator(mock_reports, skipped_filenames=["README.md"])

    print("\n" + "=" * 60)
    print("COORDINATOR FINAL VERDICT (mock test)")
    print("=" * 60)
    print(result["report"])
    print("=" * 60)