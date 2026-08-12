"""
github_fetcher.py
------------------
Day 2 module.

What this does:
Given a GitHub Pull Request link, this module:
1. Connects to GitHub using your personal access token.
2. Finds every file that changed in that PR.
3. For each changed file, collects:
   - filename
   - the diff (just the +/- changed lines)
   - the full OLD file content (before the PR)
   - the full NEW file content (after the PR)
4. Packages all of that into a "file_context" dictionary — the exact
   structure every specialist agent will read from later.

How to run this file directly (for testing):
    python github_fetcher.py

It will prompt you for a PR link in the terminal, or you can edit the
TEST_PR_URL variable at the bottom of this file.
"""

import os
import re
from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise SystemExit(
        "Missing GITHUB_TOKEN in your .env file.\n"
        "Follow Step 2 of the Day 2 guide to create one."
    )

# One authenticated connection to GitHub, reused for every call.
gh = Github(GITHUB_TOKEN)


def parse_pr_url(pr_url: str):
    """
    Turns a PR link like:
        https://github.com/octocat/Hello-World/pull/42
    into three separate pieces:
        owner = "octocat"
        repo_name = "Hello-World"
        pr_number = 42

    Why we need this: PyGithub doesn't take a URL directly — it needs
    the repo's full name ("owner/repo") and the PR number separately.
    """
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(
            f"Could not parse a valid PR URL from: {pr_url}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    owner, repo_name, pr_number = match.groups()
    return owner, repo_name, int(pr_number)


def get_file_content_at_ref(repo, filepath: str, ref: str):
    """
    Fetches the full content of one file at a specific commit (ref).

    Returns None if the file doesn't exist at that ref — this happens
    naturally for brand-new files (no "old" version) or deleted files
    (no "new" version). That's expected, not an error.
    """
    try:
        file_obj = repo.get_contents(filepath, ref=ref)
        return file_obj.decoded_content.decode("utf-8", errors="replace")
    except GithubException:
        return None


def fetch_pr_context(pr_url: str):
    """
    Main function of this module.

    Input:  a GitHub PR URL (string)
    Output: a list of file_context dictionaries, one per changed file:

        {
            "filename": "balance.py",
            "old_code": "...",   # full previous file, or None if new file
            "new_code": "...",   # full updated file, or None if deleted file
            "diff": "...",       # just the changed lines
            "status": "modified" # "added" / "removed" / "modified" / "renamed"
        }

    This is the exact structure every specialist agent (Days 3-5) and
    the Coordinator (Day 6) will consume.
    """
    owner, repo_name, pr_number = parse_pr_url(pr_url)

    print(f"Connecting to {owner}/{repo_name}, PR #{pr_number}...")
    repo = gh.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(pr_number)

    base_sha = pr.base.sha  # commit before the changes
    head_sha = pr.head.sha  # commit after the changes

    file_contexts = []

    for f in pr.get_files():
        old_code = None
        new_code = None

        # A file that isn't brand-new has an "old" version to fetch.
        if f.status != "added":
            old_code = get_file_content_at_ref(repo, f.filename, base_sha)

        # A file that wasn't deleted has a "new" version to fetch.
        if f.status != "removed":
            new_code = get_file_content_at_ref(repo, f.filename, head_sha)

        file_context = {
            "filename": f.filename,
            "old_code": old_code,
            "new_code": new_code,
            "diff": f.patch,  # PyGithub already gives us just the changed lines
            "status": f.status,
        }
        file_contexts.append(file_context)

    return file_contexts


PYTHON_EXTENSIONS = (".py",)


def filter_python_files(file_contexts):
    """
    Splits the full list of changed files into two groups:

      - python_files:  files ending in .py — these go to the 7 specialist
                        agents (Bug-Hunter, Style, Test Coverage, etc.)
      - skipped_files:  everything else (filenames only) — these do NOT
                        get sent to the Python-based static analysis agents

    Why keep a "skipped" list instead of just deleting non-Python files:
    Silently dropping files with no explanation looks like a bug, not a
    feature. Keeping the filenames lets the Coordinator's final report say
    something like:
        "3 files skipped (not Python): App.tsx, style.css, README.md"
    so the developer understands why those files weren't reviewed, instead
    of wondering if the tool missed them.

    Note: the Security Agent's secret/credential-leak check (e.g. finding
    a committed .env or .pem file) is the one exception — that check runs
    on ALL files, including the skipped ones, since secrets can appear in
    any file type. That check should receive the full, unfiltered
    file_contexts list separately, not just python_files.
    """
    python_files = []
    skipped_files = []

    for fc in file_contexts:
        if fc["filename"].endswith(PYTHON_EXTENSIONS):
            python_files.append(fc)
        else:
            skipped_files.append(fc["filename"])

    return python_files, skipped_files


def print_summary(file_contexts):
    """Small helper to print a clean, readable summary in the terminal."""
    print(f"\nFound {len(file_contexts)} changed file(s):\n")
    for fc in file_contexts:
        print(f"  - {fc['filename']}  [{fc['status']}]")
        old_len = len(fc["old_code"]) if fc["old_code"] else 0
        new_len = len(fc["new_code"]) if fc["new_code"] else 0
        diff_len = len(fc["diff"]) if fc["diff"] else 0
        print(f"      old_code: {old_len} chars | new_code: {new_len} chars | diff: {diff_len} chars")
    print()


if __name__ == "__main__":
    # The test PR link is read from your .env file (TEST_PR_URL) instead of
    # being hardcoded here. This keeps any specific project/repo links out
    # of the committed code — safer and cleaner for a public portfolio repo.
    TEST_PR_URL = os.getenv("TEST_PR_URL")

    if not TEST_PR_URL:
        raise SystemExit(
            "Missing TEST_PR_URL in your .env file.\n"
            "Add a line like:\n"
            "  TEST_PR_URL=https://github.com/owner/repo/pull/1\n"
            "then run this script again."
        )

    contexts = fetch_pr_context(TEST_PR_URL)
    print_summary(contexts)

    # Print the full context of the first file so you can see the
    # exact structure being produced.
    if contexts:
        print("--- Full file_context for first changed file ---")
        print(contexts[0])

    # Preview of the Day 6 filtering step (not wired into the pipeline yet,
    # just demonstrated here so you can see it working on real PR data).
    python_files, skipped_files = filter_python_files(contexts)
    print(f"\n{len(python_files)} Python file(s) would go to the agents.")
    if skipped_files:
        print(f"{len(skipped_files)} file(s) would be skipped (not Python): {skipped_files}")