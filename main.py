"""
main.py
--------
Day 7 module — exposes the entire multi-agent review pipeline (graph.py)
as a proper HTTP API using FastAPI.

Endpoints:
    GET  /            — simple health check
    POST /review       — takes a PR link, runs the full pipeline, returns
                          the Coordinator's final report as JSON

Error handling covers the three cases called out in the original project
plan:
    1. Invalid PR link            → 400 Bad Request
    2. GitHub errors (rate limit, — 404 / 429, with a clear message
       PR/repo not found)
    3. LLM API failure             → handled automatically by
                                     llm_client.py's Groq→Gemini fallback
                                     (Day 7); if BOTH providers fail, that
                                     surfaces here as a 502 Bad Gateway.

How to run:
    uvicorn main:app --reload
    (or just: python main.py)

Then open http://127.0.0.1:8000/docs for the interactive Swagger UI,
where you can test the /review endpoint directly in your browser.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from github.GithubException import GithubException

from graph import build_graph

load_dotenv()

app = FastAPI(
    title="DiffReview: Multi-Agent Code Review API",
    description="Submit a GitHub PR link and get back a full, AI-generated code review.",
    version="1.0.0",
)

# DAY 10: needed once the frontend (Streamlit Community Cloud) and backend
# (Render) live on two different domains — without this, the browser
# blocks the frontend's requests to the backend as a cross-origin request.
# allow_origins=["*"] is fine for a public portfolio demo with no private
# data; a real production app would list only its actual frontend URL(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The graph is built once at startup, not on every request — building it
# is cheap (just wiring functions together), so there's no need to
# rebuild it per request.
review_graph = build_graph()


class ReviewRequest(BaseModel):
    pr_url: str = Field(
        ...,
        description="A GitHub Pull Request URL",
        examples=["https://github.com/owner/repo/pull/123"],
    )


class AgentFinding(BaseModel):
    filename: str
    report: str


# DAY 8 UPDATE: maps each specialist node's state key to the short name
# used in the API response and, later, the Streamlit UI. Kept as one
# central list so adding an 8th agent later only means one new line here.
AGENT_STATE_KEYS = [
    ("bug_hunter", "bug_hunter_reports"),
    ("security", "security_reports"),
    ("style", "style_reports"),
    ("test_coverage", "test_coverage_reports"),
    ("documentation", "documentation_reports"),
    ("performance", "performance_reports"),
    ("dependency", "dependency_reports"),
]


class ReviewResponse(BaseModel):
    pr_url: str
    final_report: str
    agent_reports: dict[str, list[AgentFinding]]
    python_files_reviewed: list[str]
    files_skipped: list[str]


@app.get("/")
def health_check():
    """Simple health check — confirms the API is running."""
    return {"status": "ok", "service": "diffreview-multi-agent-code-review-api"}


@app.post("/review", response_model=ReviewResponse)
def review_pull_request(request: ReviewRequest):
    """
    Runs the full 7-agent + Coordinator pipeline on a GitHub PR and
    returns the final report.

    This one endpoint call can take a while (multiple agents, each
    running tool subprocesses plus an LLM call, across every changed
    file) — that's expected, not a bug.
    """
    pr_url = request.pr_url.strip()

    # --- Case 1: invalid PR link format ---
    if "github.com" not in pr_url or "/pull/" not in pr_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid PR URL. Expected format: "
                "https://github.com/owner/repo/pull/123"
            ),
        )

    try:
        final_state = review_graph.invoke({"pr_url": pr_url})

    except ValueError as e:
        # Raised by github_fetcher.parse_pr_url() for a malformed URL
        # that slipped past the basic check above.
        raise HTTPException(status_code=400, detail=str(e))

    except GithubException as e:
        # Raised by PyGithub for things like: PR/repo not found (404),
        # or GitHub API rate limit hit (403/429).
        status = e.status
        if status == 404:
            raise HTTPException(
                status_code=404,
                detail=f"PR or repository not found: {pr_url}",
            )
        elif status in (403, 429):
            raise HTTPException(
                status_code=429,
                detail=(
                    "GitHub API rate limit hit. Wait a bit and try again, "
                    "or confirm your GITHUB_TOKEN is set correctly."
                ),
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API error ({status}): {e.data}",
            )

    except RuntimeError as e:
        # Raised by llm_client.invoke_with_fallback() only when BOTH
        # Groq AND Gemini fail — a genuine "both providers are down"
        # situation, not a normal single-provider hiccup (which is
        # already handled silently by the fallback itself).
        raise HTTPException(
            status_code=502,
            detail=f"Both LLM providers (Groq and Gemini) failed: {e}",
        )

    except Exception as e:
        # Catch-all for anything unexpected, so the API always returns
        # a clean JSON error instead of a raw stack trace.
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    agent_reports = {
        agent_name: final_state.get(state_key, [])
        for agent_name, state_key in AGENT_STATE_KEYS
    }

    return ReviewResponse(
        pr_url=pr_url,
        final_report=final_state["final_report"],
        agent_reports=agent_reports,
        python_files_reviewed=[fc["filename"] for fc in final_state.get("python_files", [])],
        files_skipped=[fc["filename"] for fc in final_state.get("skipped_files", [])],
    )


if __name__ == "__main__":
    import uvicorn

    # DAY 10: deployment platforms like Render assign a port dynamically
    # via the PORT environment variable — binding to a hardcoded 8000
    # would fail there. Locally, this just falls back to 8000 as before.
    # Binding to 0.0.0.0 (not 127.0.0.1) is required for the app to be
    # reachable from outside its own container once deployed.
    port = int(os.getenv("PORT", 8000))
    print(f"Starting API on port {port}")
    print(f"Interactive docs available at http://127.0.0.1:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)