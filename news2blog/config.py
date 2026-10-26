"""Central configuration. Everything is overridable via environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- Provider ----
# groq (default) or openai. Groq's free tier limits tokens PER MODEL (about 8K tokens/min, 200K/day on gpt-oss),
# so the roles are spread over different models: each one draws on its own rate-limit bucket.
PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
LLM_KEY_NAME = "GROQ_API_KEY" if PROVIDER == "groq" else "OPENAI_API_KEY"

# Preference list per role: the first model your key can actually use wins (checked against Groq at startup,
# because which models an account can see varies). Setting a role in .env pins it.
_PREFERENCES = {
    "groq": {
        "MODEL": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.8-27b"],          # drafter + Day-1 agent
        "RESEARCHER_MODEL": ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "openai/gpt-oss-120b"],  # tool loop
        # checker: must be a different model from the drafter. qwen3.8-27b was tried first (different family) but
        # returned empty verdict lists on Groq, so the reliable gpt-oss-20b leads and qwen is the last backup.
        "CHECKER_MODEL": ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "minimaxai/minimax-m2.7",
                          "meta-models/muse-spark-open", "qwen/qwen3.8-27b"],
        "REPORTER_MODEL": ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "openai/gpt-oss-120b"],
        # judge (eval only): never the checker's model; the strongest reliable model left
        "JUDGE_MODEL": ["llama-3.3-70b-versatile", "minimaxai/minimax-m2.7", "openai/gpt-oss-120b",
                        "meta-models/muse-spark-open", "qwen/qwen3.8-27b"],
    },
    "openai": {
        "MODEL": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini"],
        "RESEARCHER_MODEL": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini"],
        # checker: a different model from the drafter, same rule as on Groq
        "CHECKER_MODEL": ["gpt-4.1-mini", "gpt-4o", "gpt-5-mini"],
        "REPORTER_MODEL": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini"],
        "JUDGE_MODEL": ["gpt-4o", "gpt-4.1", "gpt-5"],  # stronger than both, and never the checker
    },
}[PROVIDER]
ROLES = list(_PREFERENCES)
_PINNED = {r for r in ROLES if os.getenv(r)}

MODEL = os.getenv("MODEL", _PREFERENCES["MODEL"][0])
RESEARCHER_MODEL = os.getenv("RESEARCHER_MODEL", _PREFERENCES["RESEARCHER_MODEL"][0])
CHECKER_MODEL = os.getenv("CHECKER_MODEL", _PREFERENCES["CHECKER_MODEL"][0])
REPORTER_MODEL = os.getenv("REPORTER_MODEL", _PREFERENCES["REPORTER_MODEL"][0])
JUDGE_MODEL = os.getenv("JUDGE_MODEL", _PREFERENCES["JUDGE_MODEL"][0])
# backups tried in order if the checker model keeps failing (set by resolve_models)
CHECKER_FALLBACKS: list[str] = [m for m in _PREFERENCES["CHECKER_MODEL"] if m not in (CHECKER_MODEL, MODEL)][:2]


def available_models() -> list[str]:
    """Model IDs this API key can use (one cheap API call)."""
    if PROVIDER == "groq":
        from groq import Groq

        return sorted(m.id for m in Groq().models.list().data)
    from openai import OpenAI

    return sorted(m.id for m in OpenAI().models.list().data)


def resolve_models(verbose: bool = True) -> dict[str, str]:
    """Pick, for each role, the first preferred model the key can access. Fails clearly if a pinned model is missing."""
    g = globals()
    try:
        avail = set(available_models())
    except Exception as e:  # network hiccup: keep defaults and let the call itself report
        if verbose:
            print(f"(could not list {PROVIDER} models: {str(e)[:120]}; using defaults)")
        return {r: g[r] for r in ROLES}
    for role in ROLES:
        if role in _PINNED:
            if g[role] not in avail:
                raise SystemExit(f"{role}={g[role]} in .env is not available to your {PROVIDER} key.\n"
                                 f"Available: {', '.join(sorted(avail))}")
            continue
        prefs = [m for m in _PREFERENCES[role] if m in avail]
        if role == "CHECKER_MODEL":  # avoid the drafter's model if any alternative exists
            prefs = [m for m in prefs if m != g["MODEL"]] or prefs
        if role == "JUDGE_MODEL":
            prefs = [m for m in prefs if m != g["CHECKER_MODEL"]] or prefs
        if not prefs:
            raise SystemExit(f"None of the models for {role} are available to your {PROVIDER} key ({_PREFERENCES[role]}).\n"
                             f"Available: {', '.join(sorted(avail))}\nSet {role}=<one of these> in .env.")
        g[role] = prefs[0]
    # backups never include the drafter's model: we'd rather fail than let the drafter grade itself
    g["CHECKER_FALLBACKS"] = [m for m in _PREFERENCES["CHECKER_MODEL"] if m in avail and m not in (g["CHECKER_MODEL"], g["MODEL"])][:2]
    chosen = {r: g[r] for r in ROLES}
    if verbose:
        print("Models: " + ", ".join(f"{r.replace('_MODEL', '').lower()}={m}" for r, m in chosen.items()))
    return chosen

# gpt-oss models are reasoning models; "low" keeps hidden reasoning tokens (which count against TPM) small.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "3000"))

# Retry policy: 1 first draft + MAX_RETRIES rewrites, then report failure
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

# Research limits. Sized so the biggest prompt (drafter revision / checker) stays under Groq's ~8K tokens/minute.
NUM_EXTRA_SOURCES = 2
MIN_CLAIMS = int(os.getenv("MIN_CLAIMS", "4"))  # a checker-approved post needs at least this many cited facts
MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "3000" if PROVIDER == "groq" else "12000"))
# Client-side pacing: tokens per minute allowed per model (0 = off). Groq free tier is about 8K on gpt-oss.
TPM_LIMIT = int(os.getenv("TPM_LIMIT", "7500" if PROVIDER == "groq" else "0"))
MIN_ARTICLE_CHARS = 400
RESEARCHER_MAX_STEPS = 8
TOOL_PREVIEW_CHARS = 600  # what the researcher LLM sees of a fetched page

RUNS_DIR = ROOT / "runs"
TONE_GUIDE_PATH = ROOT / "tone_guide.md"

# USD per 1M tokens (input, output).
# Groq: https://console.groq.com/docs/models (checked 2026-10-25). Llama models are listed as "contact sales";
# on the free tier they cost $0, so we report $0 rather than guess.
PRICES = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.80, 4.00),
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "llama-3.1-8b-instant": (0.0, 0.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
}
# Tavily pay-as-you-go price per API credit (basic search = 1 credit, extract = 1 credit / 5 URLs).
# The free tier (1,000 credits/month) makes this $0 in practice; we still report it.
TAVILY_USD_PER_CREDIT = float(os.getenv("TAVILY_USD_PER_CREDIT", "0.008"))


def price_for(model: str) -> tuple[float, float]:
    if model in PRICES:
        return PRICES[model]
    for name in sorted(PRICES, key=len, reverse=True):
        if model.startswith(name):
            return PRICES[name]
    return (0.0, 0.0)


def require_keys(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)}. Copy .env.example to .env and fill them in.")
