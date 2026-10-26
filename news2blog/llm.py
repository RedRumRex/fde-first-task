"""Thin wrapper around the chat model so every call is logged, costed and retried sensibly.

Agents call `llm.structured(...)` and `llm.tool_step(...)` through this module, which also lets the
offline tests swap in a fake model with monkeypatch."""
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any, Type, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from . import config
from .runlog import RunLogger

T = TypeVar("T", bound=BaseModel)
_NO_REASONING_PARAM: set[str] = set()  # models that rejected the reasoning_effort setting


def _chat(model: str, temperature: float = 0.0, max_tokens: int | None = None):
    if config.PROVIDER == "groq":
        from langchain_groq import ChatGroq

        kwargs: dict[str, Any] = {"model": model, "temperature": temperature, "max_retries": 6,
                                  "request_timeout": 180, "max_tokens": max_tokens or config.MAX_OUTPUT_TOKENS}
        if model not in _NO_REASONING_PARAM:
            if model.startswith("openai/gpt-oss"):
                kwargs["reasoning_effort"] = config.REASONING_EFFORT
            elif model.startswith("qwen/"):
                kwargs["reasoning_effort"] = "none"  # Qwen "thinking" tokens would eat the per-minute budget
        return ChatGroq(**kwargs)

    from langchain_openai import ChatOpenAI

    kwargs = {"model": model, "max_retries": 3, "timeout": 180}
    if not (model.startswith("gpt-5") or model.startswith("o")):  # reasoning models only take default temperature
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def _record(log: RunLogger, node: str, model: str, msg: AIMessage | None) -> None:
    um = getattr(msg, "usage_metadata", None) or {}
    log.add_usage(node, model, int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0)))


def _total(msg: AIMessage | None) -> int:
    um = getattr(msg, "usage_metadata", None) or {}
    return int(um.get("input_tokens", 0)) + int(um.get("output_tokens", 0))


class LLMError(RuntimeError):
    pass


class BadGeneration(RuntimeError):
    """The model produced an invalid tool call / JSON (Groq 400 tool_use_failed, json_validate_failed...)."""


# Groq models with native JSON-schema structured outputs: far more reliable than function calling for nested
# schemas (function calling made qwen degenerate into thousands of '\r' characters on the checker's verdict list).
_JSON_SCHEMA_PREFIXES = ("openai/gpt-oss", "qwen/qwen3.8", "meta-models/muse")


def _methods_for(model: str) -> list[str]:
    if config.PROVIDER == "groq" and model.startswith(_JSON_SCHEMA_PREFIXES):
        return ["json_schema", "json_schema", "function_calling"]
    return ["function_calling"] * 3


# ---- client-side pacing: keep each model under its tokens-per-minute budget instead of hammering 429s ----
_usage_window: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _estimate(messages: list[BaseMessage], max_tokens: int) -> int:
    chars = sum(len(m.content if isinstance(m.content, str) else str(m.content)) for m in messages)
    return chars // 4 + 600 + max_tokens  # + schema/tool definitions overhead


def _wait_needed(model: str, est: int) -> float:
    """Seconds until `est` tokens fit in this model's one-minute window (0 = fits now)."""
    if not config.TPM_LIMIT:
        return 0.0
    with _lock:
        q = _usage_window[model]
        now = time.time()
        while q and now - q[0][0] > 60:
            q.popleft()
        used = sum(n for _, n in q)
        if used == 0 or used + est <= config.TPM_LIMIT:
            return 0.0
        return 60 - (now - q[0][0]) + 0.5


def pick_model(pool: list[str], est: int) -> str:
    """From models that can do the job, take the one that can run soonest (spreads load over rate-limit buckets)."""
    return min(dict.fromkeys(pool), key=lambda m: _wait_needed(m, est))


def _throttle(log: RunLogger, node: str, model: str, est: int) -> None:
    limit = config.TPM_LIMIT
    if not limit:
        return
    waited = 0.0
    while True:
        with _lock:
            q = _usage_window[model]
            now = time.time()
            while q and now - q[0][0] > 60:
                q.popleft()
            used = sum(n for _, n in q)
            if used == 0 or used + est <= limit:
                q.append((now, est))  # reserve; replaced by the real count after the call
                if waited:
                    log.event(node, "throttle", f"waited {waited:.0f}s to stay under {limit} tokens/min on {model}")
                return
            wait = 60 - (now - q[0][0]) + 0.5
        time.sleep(wait)
        waited += wait


def _settle(model: str, est: int, actual: int) -> None:
    with _lock:
        q = _usage_window[model]
        for i in range(len(q) - 1, -1, -1):
            if q[i][1] == est:
                q[i] = (q[i][0], actual or est)
                break


def _classify(e: Exception) -> str:
    """Map provider errors to: 'retry' (model produced a bad tool call), 'wait' (per-minute limit), or 'fatal'."""
    msg = str(e).lower()
    status = getattr(e, "status_code", None)
    # NB: OpenAI's ordinary rate-limit message also mentions billing, so match only the real quota codes
    if "insufficient_quota" in msg or "credit_balance" in msg or "no credits remaining" in msg:
        return "billing"
    if status == 400 and "reasoning" in msg:
        return "drop_reasoning"
    if status == 404 or "model_not_found" in msg or "does not exist" in msg:
        return "no_model"
    if status == 413 or "request too large" in msg or "reduce your message size" in msg:
        return "too_large"
    if "tokens per day" in msg or "(tpd)" in msg or "requests per day" in msg:
        return "daily"
    if status == 429 or "rate limit" in msg:
        return "wait"
    if "tool_use_failed" in msg or "failed to call a function" in msg or "output_parse_failed" in msg or "json_validate_failed" in msg:
        return "retry"
    if status is not None and status >= 500:
        return "wait"
    return "fatal"


def _invoke(log: RunLogger, node: str, model: str, fn, attempts: int = 4, raise_bad_generation: bool = False):
    """Call fn() and recover from the errors that are worth recovering from."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - provider SDKs raise many types
            kind = _classify(e)
            if kind == "drop_reasoning" and model not in _NO_REASONING_PARAM:
                _NO_REASONING_PARAM.add(model)
                log.event(node, "llm_retry", f"{model} rejected the reasoning setting; retrying without it")
                continue
            if kind == "no_model":
                raise LLMError(f"{node}: model '{model}' is not available to your API key. Run `python run.py --models` "
                               f"to see what you can use, and set it in .env.") from e
            if kind == "too_large":
                raise LLMError(f"{node}: prompt is bigger than {model}'s tokens-per-minute limit. "
                               f"Lower MAX_SOURCE_CHARS in .env (now {config.MAX_SOURCE_CHARS}). Detail: {str(e)[:200]}") from e
            if kind == "billing":
                raise LLMError(f"{node}: the {config.PROVIDER} account has no credits/quota left (billing). Add credits, or switch "
                               f"LLM_PROVIDER in .env. Detail: {str(e)[:160]}") from e
            if kind == "daily":
                raise LLMError(f"{node}: {model} hit its DAILY token limit on {config.PROVIDER} (per-day tokens or requests). "
                               f"Wait for the reset, switch the role to another model in .env, or raise the account's tier "
                               f"(OpenAI: add a payment method; Groq: Developer plan). Detail: {str(e)[:300]}") from e
            if kind == "retry" and raise_bad_generation:
                raise BadGeneration(str(e)[:400]) from e
            if kind == "fatal" or i == attempts - 1:
                raise
            m = re.search(r"try again in ([\d.]+)s", str(e))
            wait = float(m.group(1)) + 1 if m else (20 * (i + 1) if kind == "wait" else 1)
            log.event(node, "llm_retry", f"{kind}: {str(e)[:140]} (waiting {wait:.0f}s)")
            time.sleep(min(wait, 90))
    raise LLMError(f"{node}: gave up after {attempts} attempts")


def structured(
    log: RunLogger,
    node: str,
    schema: Type[T],
    messages: list[BaseMessage],
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> T:
    """One LLM call that must return `schema`.

    Tries JSON-schema mode first on models that support it, then function calling; feeds the error back each time."""
    model = model or config.MODEL
    max_tokens = max_tokens or config.MAX_OUTPUT_TOKENS
    msgs = list(messages)
    last_err = ""
    for attempt, method in enumerate(_methods_for(model)):
        def call():
            r = _chat(model, temperature, max_tokens).with_structured_output(schema, method=method, include_raw=True)
            return r.invoke(msgs)

        est = _estimate(msgs, max_tokens)
        _throttle(log, node, model, est)
        try:
            out = _invoke(log, node, model, call, raise_bad_generation=True)
        except BadGeneration as e:
            _settle(model, est, est)
            last_err = str(e)
            log.event(node, "parse_error", f"{model} produced invalid {method} output (attempt {attempt + 1}); retrying")
            msgs = list(messages) + [HumanMessage(
                f"Your previous answer was not valid JSON for {schema.__name__}. Return ONLY valid JSON matching the schema. "
                "Keep every 'reason' under 25 words. No extra whitespace, no repeated characters.")]
            continue
        _record(log, node, model, out.get("raw"))
        _settle(model, est, _total(out.get("raw")))
        if out.get("parsed") is not None and out.get("parsing_error") is None:
            return out["parsed"]
        last_err = str(out.get("parsing_error") or "no structured output returned")
        log.event(node, "parse_error", f"structured output failed (attempt {attempt + 1}, {method}): {last_err[:200]}")
        msgs = list(messages) + [HumanMessage(f"Your last output did not match the required schema: {last_err[:500]}. "
                                              f"Return valid {schema.__name__} JSON.")]
    raise LLMError(f"{node}: {model} failed to return valid {schema.__name__} after 3 attempts: {last_err[:200]}")


def tool_step(log: RunLogger, node: str, messages: list[BaseMessage], tools: list, model: str | None = None,
              pool: list[str] | None = None) -> AIMessage:
    """One step of a tool-calling loop: the model either calls tools or answers.
    With `pool`, the step runs on whichever model in the pool has rate-limit room soonest."""
    est = _estimate(messages, 700)
    model = pick_model(pool, est) if pool else (model or config.MODEL)
    _throttle(log, node, model, est)
    ai = _invoke(log, node, model, lambda: _chat(model, max_tokens=700).bind_tools(tools).invoke(messages))
    _record(log, node, model, ai)
    _settle(model, est, _total(ai))
    return ai
