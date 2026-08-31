"""
app.py
-------
Day 8 module — the Streamlit demo interface. This is the app recruiters
and interviewers will actually click through: paste a PR link, click
"Run Review", and see all 7 agents' findings plus the Coordinator's
final verdict, cleanly displayed.

This file calls the FastAPI backend (main.py, Day 7) over HTTP — it
does NOT import graph.py or the agents directly. That separation means
the backend could run on a different machine/server entirely and this
UI wouldn't need to change.

How to run:
    1. In one terminal: uvicorn main:app --reload
    2. In another terminal: streamlit run app.py
"""

import os

import requests
import streamlit as st

st.set_page_config(
    page_title="Multi-Agent Code Reviewer",
    page_icon="🤖",
    layout="wide",
)

# The backend URL is configurable via an environment variable so this
# same file works locally (default) and once deployed (Day 10), where
# the frontend and backend usually live at different URLs.
BACKEND_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000")

# Icon + display name for each agent — used to build the expandable
# sections. Keeping this as one lookup table means adding an 8th agent
# later is a one-line change here, not a restructure of the whole file.
AGENT_DISPLAY = {
    "bug_hunter": {"label": "Bug-Hunter", "icon": "🐛"},
    "security": {"label": "Security", "icon": "🔒"},
    "style": {"label": "Style / Readability", "icon": "🎨"},
    "test_coverage": {"label": "Test Coverage", "icon": "🧪"},
    "documentation": {"label": "Documentation", "icon": "📝"},
    "performance": {"label": "Performance", "icon": "⚡"},
    "dependency": {"label": "Dependency / License", "icon": "📦"},
}


def severity_badge(report_text: str) -> str:
    """
    A lightweight, best-effort severity indicator for a single agent
    report — just scans the text for the severity words the agents'
    prompts already ask them to use (Critical/Major/Minor). This is
    intentionally simple text matching, not a parser — good enough for
    a quick visual cue in the UI, not a source of truth.
    """
    lowered = report_text.lower()
    if "critical" in lowered:
        return "🔴 Critical mentioned"
    elif "major" in lowered:
        return "🟠 Major mentioned"
    elif "minor" in lowered:
        return "🟡 Minor mentioned"
    else:
        return "🟢 No issues flagged"


# ---------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------

st.title("🤖 Multi-Agent Code Review")
st.caption(
    "Paste a GitHub Pull Request link to get an instant, AI-powered review "
    "from a 7-agent team — the same rigor a large engineering org's review "
    "process would provide, in one automated pass."
)

pr_url = st.text_input(
    "GitHub PR link",
    placeholder="https://github.com/owner/repo/pull/123",
)

run_clicked = st.button("Run Review", type="primary", disabled=not pr_url)

if run_clicked:
    with st.spinner(
        "Running 7 specialist agents + Coordinator... "
        "this can take a minute or two on larger PRs."
    ):
        try:
            response = requests.post(
                f"{BACKEND_URL}/review",
                json={"pr_url": pr_url},
                timeout=600,
            )
        except requests.exceptions.ConnectionError:
            st.error(
                f"Could not connect to the backend at {BACKEND_URL}. "
                "Is `uvicorn main:app --reload` running in another terminal?"
            )
            st.stop()

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        st.error(f"Review failed ({response.status_code}): {detail}")
        st.stop()

    data = response.json()

    # --- Final verdict, highlighted at the top ---
    st.subheader("📋 Final Verdict")
    verdict_text = data["final_report"]
    lowered_verdict = verdict_text.lower()

    if "block" in lowered_verdict or "critical" in lowered_verdict:
        st.error(verdict_text)
    elif "request changes" in lowered_verdict or "major" in lowered_verdict:
        st.warning(verdict_text)
    else:
        st.success(verdict_text)

    # --- Skipped files transparency note ---
    if data["files_skipped"]:
        st.info(
            f"⏭️ {len(data['files_skipped'])} file(s) not reviewed by the "
            f"Python-specific agents: {', '.join(data['files_skipped'])}"
        )

    st.divider()
    st.subheader("🔍 Specialist Agent Findings")
    st.caption("Expand any section below to see that agent's detailed report per file.")

    for agent_key, display in AGENT_DISPLAY.items():
        reports = data["agent_reports"].get(agent_key, [])
        header = f"{display['icon']} {display['label']} ({len(reports)} file(s) reviewed)"

        with st.expander(header):
            if not reports:
                st.write("No files were reviewed by this agent for this PR.")
            else:
                for r in reports:
                    st.markdown(f"**File: `{r['filename']}`** — {severity_badge(r['report'])}")
                    st.markdown(r["report"])
                    st.markdown("---")

    st.divider()
    st.caption(
        "💡 Full reasoning traces for every agent call are available in "
        "your LangSmith dashboard."
    )

else:
    st.info("Paste a PR link above and click **Run Review** to get started.")