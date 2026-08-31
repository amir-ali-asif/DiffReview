"""
llm_client.py
--------------
Day 7 module (updated) — a shared LLM wrapper used by every agent
instead of each agent calling ChatGroq directly.

UPDATE — fixes a real rate-limit failure hit during the build:
When graph.py fans out to all 7 specialist agents in parallel, and each
one loops over every changed file, it's possible for many large LLM
calls to fire within the same second. Groq's free tier caps this at
8000 tokens/minute, so a PR with several files could trip the limit
almost immediately. Two things were added to handle this properly:

  1. RETRY WITH BACKOFF — Groq's own 429 error message includes exactly
     how many seconds to wait ("Please try again in 2.805s"). Instead
     of immediately giving up and falling back to Gemini on every
     rate-limit hit, this now waits that long and retries Groq itself
     up to 3 times — since the limit is per-MINUTE, a few seconds is
     usually all it takes to clear.
  2. CONCURRENCY LIMITER — a semaphore caps how many Groq calls can be
     in flight across ALL agents at once (default: 2), so the 7
     parallel graph nodes queue politely instead of bursting the API
     simultaneously.

Also updated: GEMINI_MODEL to gemini-3.6-flash, since gemini-2.5-flash
was retired for new API users (confirmed via a live 404 from Google's
own API, which pointed directly at gemini-3.6-flash as the replacement).

USAGE (unchanged, from any agent file):
    from llm_client import invoke_with_fallback
    response = invoke_with_fallback(messages)
    print(response.content)
"""

import os
import re
import time
import threading

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-120b"       # Groq's recommended replacement
                                           # for the deprecated llama-3.3-70b-versatile
GEMINI_MODEL = "gemini-3.6-flash"         # updated Aug 2026 — gemini-2.5-flash
                                           # was retired for new API users

MAX_RATE_LIMIT_RETRIES = 3

_groq_llm = None
_gemini_llm = None

# Caps how many Groq calls can be in flight AT ONCE across every agent.
# graph.py runs 7 specialist nodes in parallel, each looping over every
# changed file — without this limiter, they can all fire requests at
# nearly the same instant and blow through the tokens-per-minute limit
# immediately, even before any single call is individually too large.
_groq_semaphore = threading.Semaphore(2)


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None:
        _groq_llm = ChatGroq(model=GROQ_MODEL, temperature=0)
    return _groq_llm


def _get_gemini_llm():
    global _gemini_llm
    if _gemini_llm is None:
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if not gemini_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set in .env — cannot fall back to Gemini."
            )
        _gemini_llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=gemini_key,
            temperature=0,
        )
    return _gemini_llm


def _extract_retry_seconds(error, default: float = 3.0) -> float:
    """
    Groq's rate-limit error message includes the exact wait time, e.g.
    "Please try again in 2.805s". Parses that out if present, with a
    small safety buffer added; falls back to a fixed default otherwise.
    """
    match = re.search(r"try again in ([\d.]+)s", str(error))
    if match:
        return float(match.group(1)) + 0.5
    return default


def _is_rate_limit_error(error) -> bool:
    text = str(error).lower()
    return "429" in str(error) or "rate_limit" in text or "rate limit" in text


def _invoke_groq_with_retry(messages: list):
    """
    Tries Groq, and if it hits a rate limit specifically (not any other
    error), waits the suggested amount of time and retries — up to
    MAX_RATE_LIMIT_RETRIES times — before giving up and letting the
    caller fall back to Gemini.
    """
    last_error = None
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            with _groq_semaphore:
                llm = _get_groq_llm()
                return llm.invoke(messages)
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e) and attempt < MAX_RATE_LIMIT_RETRIES:
                wait_seconds = _extract_retry_seconds(e)
                print(
                    f"[llm_client] Groq rate limit hit (attempt {attempt}/"
                    f"{MAX_RATE_LIMIT_RETRIES}). Waiting {wait_seconds:.1f}s "
                    f"before retrying..."
                )
                time.sleep(wait_seconds)
                continue
            # Not a rate limit, or out of retries — stop trying Groq.
            raise last_error
    raise last_error


def invoke_with_fallback(messages: list):
    """
    Tries Groq first (with automatic rate-limit retry). If that still
    fails after retries, falls back to Gemini. If BOTH fail, raises one
    combined error explaining what went wrong with each.
    """
    try:
        return _invoke_groq_with_retry(messages)
    except Exception as groq_error:
        print(f"[llm_client] Groq call failed after retries ({groq_error}). Falling back to Gemini...")
        try:
            llm = _get_gemini_llm()
            return llm.invoke(messages)
        except Exception as gemini_error:
            raise RuntimeError(
                f"Both Groq and Gemini failed.\n"
                f"Groq error: {groq_error}\n"
                f"Gemini error: {gemini_error}"
            )


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    print(f"Testing primary model (Groq: {GROQ_MODEL})...")
    response = invoke_with_fallback([HumanMessage(content="Reply with one short sentence.")])
    print(f"Response: {response.content}")
    print("\nIf you want to test the FALLBACK path specifically, temporarily set an")
    print("invalid GROQ_API_KEY in your .env and re-run this file — you should see")
    print("the '[llm_client] Groq call failed...' message followed by a Gemini reply.")