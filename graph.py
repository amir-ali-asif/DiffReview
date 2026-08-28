"""
graph.py
---------
Day 6 module — wires all 7 specialist agents + the Coordinator into one
LangGraph workflow. This is the first time the ENTIRE pipeline runs
end-to-end from a single PR link to one final report.

Graph shape:

                        START
                          |
                        fetch   (fetches PR, splits into python_files / skipped_files)
                          |
        ┌─────────┬─────────┬──────────────┬───────────────┬─────────────┬────────────┐
        |         |         |              |               |             |            |
   bug_hunter  security   style   test_coverage   documentation   performance   dependency
        |         |         |              |               |             |            |
        └─────────┴─────────┴──────────────┴───────────────┴─────────────┴────────────┘
                          |
                     coordinator
                          |
                         END

The 7 specialist nodes all run right after "fetch" and all feed into
"coordinator" — LangGraph automatically runs them in parallel and waits
for all 7 to finish before running "coordinator" (a "fan-out, fan-in"
pattern), since none of the specialist agents depend on each other's
output.

Each specialist NODE internally loops over the relevant files and calls
its agent function once per file — so one graph node still produces
multiple reports if a PR changes multiple files.

Two routing details carried over from Day 5, now actually wired in:
  - security_node runs on python_files AND skipped_files, since its
    secret-leak scan needs to see every file regardless of language.
  - dependency_node also runs on python_files AND skipped_files, since
    dependency manifests (requirements.txt, etc.) are never .py files;
    the agent internally no-ops on anything that isn't a manifest file,
    so graph.py doesn't need its own separate filtering logic for this.
"""

import os
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from github_fetcher import fetch_pr_context, filter_python_files
from agents.bug_hunter import run_bug_hunter
from agents.security import run_security
from agents.style import run_style
from agents.test_coverage import run_test_coverage
from agents.documentation import run_documentation
from agents.performance import run_performance
from agents.dependency import run_dependency
from agents.coordinator import run_coordinator

load_dotenv()


class ReviewState(TypedDict):
    pr_url: str
    file_contexts: list
    python_files: list
    skipped_files: list
    bug_hunter_reports: list
    security_reports: list
    style_reports: list
    test_coverage_reports: list
    documentation_reports: list
    performance_reports: list
    dependency_reports: list
    final_report: str


# ---------------------------------------------------------------------
# Node: fetch
# ---------------------------------------------------------------------

def fetch_node(state: ReviewState) -> dict:
    print(f"\n[Graph] Fetching PR: {state['pr_url']}")
    file_contexts = fetch_pr_context(state["pr_url"])
    python_files, skipped_files = filter_python_files(file_contexts)

    print(
        f"[Graph] {len(python_files)} Python file(s), "
        f"{len(skipped_files)} non-Python file(s) set aside by the filter."
    )

    return {
        "file_contexts": file_contexts,
        "python_files": python_files,
        "skipped_files": skipped_files,
    }


# ---------------------------------------------------------------------
# Specialist nodes — each loops over its relevant files
# ---------------------------------------------------------------------

def bug_hunter_node(state: ReviewState) -> dict:
    reports = [run_bug_hunter(fc) for fc in state["python_files"]]
    return {"bug_hunter_reports": reports}


def security_node(state: ReviewState) -> dict:
    # Runs on EVERY file (python + skipped) — the secret scan inside
    # run_security needs to see non-Python files too.
    all_files = state["python_files"] + state["skipped_files"]
    reports = [run_security(fc) for fc in all_files]
    return {"security_reports": reports}


def style_node(state: ReviewState) -> dict:
    reports = [run_style(fc) for fc in state["python_files"]]
    return {"style_reports": reports}


def test_coverage_node(state: ReviewState) -> dict:
    reports = [run_test_coverage(fc) for fc in state["python_files"]]
    return {"test_coverage_reports": reports}


def documentation_node(state: ReviewState) -> dict:
    reports = [run_documentation(fc) for fc in state["python_files"]]
    return {"documentation_reports": reports}


def performance_node(state: ReviewState) -> dict:
    reports = [run_performance(fc) for fc in state["python_files"]]
    return {"performance_reports": reports}


def dependency_node(state: ReviewState) -> dict:
    # Runs on EVERY file too — run_dependency internally no-ops on
    # anything that isn't a recognized dependency manifest file, so no
    # separate filtering is needed here.
    all_files = state["python_files"] + state["skipped_files"]
    reports = [run_dependency(fc) for fc in all_files]
    return {"dependency_reports": reports}


# ---------------------------------------------------------------------
# Node: coordinator
# ---------------------------------------------------------------------

def coordinator_node(state: ReviewState) -> dict:
    all_reports = (
        state.get("bug_hunter_reports", [])
        + state.get("security_reports", [])
        + state.get("style_reports", [])
        + state.get("test_coverage_reports", [])
        + state.get("documentation_reports", [])
        + state.get("performance_reports", [])
        + state.get("dependency_reports", [])
    )

    skipped_filenames = [fc["filename"] for fc in state.get("skipped_files", [])]

    result = run_coordinator(all_reports, skipped_filenames)
    return {"final_report": result["report"]}


# ---------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------

def build_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("fetch", fetch_node)
    builder.add_node("bug_hunter", bug_hunter_node)
    builder.add_node("security", security_node)
    builder.add_node("style", style_node)
    builder.add_node("test_coverage", test_coverage_node)
    builder.add_node("documentation", documentation_node)
    builder.add_node("performance", performance_node)
    builder.add_node("dependency", dependency_node)
    builder.add_node("coordinator", coordinator_node)

    builder.add_edge(START, "fetch")

    # Fan-out: fetch feeds all 7 specialist nodes, which LangGraph runs
    # in parallel since none of them depend on each other.
    specialist_nodes = [
        "bug_hunter", "security", "style", "test_coverage",
        "documentation", "performance", "dependency",
    ]
    for node_name in specialist_nodes:
        builder.add_edge("fetch", node_name)

    # Fan-in: all 7 specialist nodes must finish before coordinator runs.
    for node_name in specialist_nodes:
        builder.add_edge(node_name, "coordinator")

    builder.add_edge("coordinator", END)

    return builder.compile()


if __name__ == "__main__":
    test_pr_url = os.getenv("TEST_PR_URL")
    if not test_pr_url:
        raise SystemExit(
            "Missing TEST_PR_URL in your .env file.\n"
            "Add a line like:\n"
            "  TEST_PR_URL=https://github.com/owner/repo/pull/1"
        )

    graph = build_graph()

    print("Running the full pipeline end-to-end. This calls all 7 agents")
    print("plus the Coordinator, so it will take noticeably longer than")
    print("testing a single agent — that's expected, not a bug.\n")

    final_state = graph.invoke({"pr_url": test_pr_url})

    print("\n" + "=" * 60)
    print("FINAL COORDINATOR REPORT")
    print("=" * 60)
    print(final_state["final_report"])
    print("=" * 60)