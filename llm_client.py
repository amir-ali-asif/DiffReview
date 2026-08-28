"""
llm_client.py
--------------
Day 7 module — a shared LLM wrapper used by every agent instead of each
agent calling ChatGroq directly.

WHY THIS EXISTS:
Every agent (Days 3-6) currently does:
    llm = ChatGroq(model="...", temperature=0)
    response = llm.invoke(messages)

That works, but it means if Groq ever has an outage, hits a rate limit,
or (as already happened once in this project) deprecates a model, EVERY
agent breaks at once with no fallback. This module centralizes that
logic in ONE place: try Groq first, and if it fails for any reason,
automatically retry the same messages against Gemini instead.

This is also just good engineering practice: instead of copy-pasting
"try Groq, fall back to Gemini" into 8 different agent files, it's
written once here and imported everywhere.

USAGE (from any agent file):
    from llm_client import invoke_with_fallback
    response = invoke_with_fallback(messages)
    print(response.content)   # same .content attribute either way
"""

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-120b"      # Groq's recommended replacement
                                          # for the deprecated llama-3.3-70b-versatile
GEMINI_MODEL = "gemini-2.5-flash"        # current free-tier Gemini model
                                          # (Gemini 2.0 Flash was shut down in 2026)

_groq_llm = None
_gemini_llm = None


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


def invoke_with_fallback(messages: list):
    """
    Tries Groq first. If that call raises ANY exception (rate limit,
    outage, deprecated model, network error, etc.), logs a warning and
    retries the exact same messages against Gemini instead.

    Both ChatGroq and ChatGoogleGenerativeAI are LangChain chat models,
    so both return an object with a .content attribute — callers don't
    need to change anything about how they read the response.
    """
    try:
        llm = _get_groq_llm()
        return llm.invoke(messages)
    except Exception as groq_error:
        print(f"[llm_client] Groq call failed ({groq_error}). Falling back to Gemini...")
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
    # Quick standalone test: confirms the primary path works.
    from langchain_core.messages import HumanMessage

    print(f"Testing primary model (Groq: {GROQ_MODEL})...")
    response = invoke_with_fallback([HumanMessage(content="Reply with one short sentence.")])
    print(f"Response: {response.content}")
    print("\nIf you want to test the FALLBACK path specifically, temporarily set an")
    print("invalid GROQ_API_KEY in your .env and re-run this file — you should see")
    print("the '[llm_client] Groq call failed...' message followed by a Gemini reply.")
