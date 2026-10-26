"""Model resolution against what the API key can see, and error classification."""
import importlib

import pytest

from news2blog import config, llm


@pytest.fixture
def fresh_config(monkeypatch):
    for r in ["MODEL", "RESEARCHER_MODEL", "CHECKER_MODEL", "REPORTER_MODEL", "JUDGE_MODEL"]:
        monkeypatch.delenv(r, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")  # set vars win over .env, so the developer's .env can't leak in
    mod = importlib.reload(config)
    yield mod
    importlib.reload(config)


def test_account_without_llama(fresh_config, monkeypatch):
    # what Yash's key returned: no llama-3.3-70b-versatile
    monkeypatch.setattr(fresh_config, "available_models",
                        lambda: ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "whisper-large-v3"])
    m = fresh_config.resolve_models(verbose=False)
    assert m["MODEL"] == "openai/gpt-oss-120b"
    assert m["CHECKER_MODEL"] == "openai/gpt-oss-20b"        # not the drafter's model; qwen proved unreliable
    assert m["CHECKER_MODEL"] != m["MODEL"]
    assert m["JUDGE_MODEL"] != m["CHECKER_MODEL"]
    assert fresh_config.CHECKER_FALLBACKS == ["qwen/qwen3.8-27b"]  # never the drafter's model
    assert fresh_config.CHECKER_MODEL == "openai/gpt-oss-20b"   # globals updated for the agents


def test_pinned_missing_model_fails_clearly(fresh_config, monkeypatch):
    monkeypatch.setattr(fresh_config, "_PINNED", {"CHECKER_MODEL"})
    monkeypatch.setattr(fresh_config, "CHECKER_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(fresh_config, "available_models", lambda: ["openai/gpt-oss-120b"])
    with pytest.raises(SystemExit, match="not available"):
        fresh_config.resolve_models(verbose=False)


class E(Exception):
    def __init__(self, m, c=None):
        super().__init__(m)
        self.status_code = c


@pytest.mark.parametrize("err,kind", [
    (E("The model `llama-3.3-70b-versatile` does not exist or you do not have access to it. model_not_found", 404), "no_model"),
    (E("reasoning_effort is not supported for this model", 400), "drop_reasoning"),
    (E("Rate limit reached ... tokens per minute (TPM): Limit 8000. Please try again in 7.5s", 429), "wait"),
    (E("Rate limit reached for model on tokens per day (TPD): Limit 200000", 429), "daily"),
    (E("Request too large for model", 413), "too_large"),
    (E("{'code': 'tool_use_failed'}", 400), "retry"),
])
def test_classify(err, kind):
    assert llm._classify(err) == kind


def test_structured_switches_method_after_bad_generations(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage, HumanMessage
    from news2blog.runlog import RunLogger
    from news2blog.schemas import EventBrief

    monkeypatch.setattr(config, "PROVIDER", "groq")
    monkeypatch.setattr(config, "TPM_LIMIT", 0)
    tried = []

    class FakeRunnable:
        def __init__(self, method):
            self.method = method

        def invoke(self, msgs):
            tried.append(self.method)
            if self.method == "json_schema":
                raise E("Error code: 400 - {'code': 'tool_use_failed', 'failed_generation': '\\r\\r\\r'}", 400)
            brief = EventBrief(headline="h", event_date="d", key_entities=["a"], search_queries=["q"])
            return {"raw": AIMessage(content="", usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
                    "parsed": brief, "parsing_error": None}

    class FakeChat:
        def with_structured_output(self, schema, method, include_raw):
            return FakeRunnable(method)

    monkeypatch.setattr(llm, "_chat", lambda *a, **k: FakeChat())
    log = RunLogger(base=tmp_path, quiet=True)
    out = llm.structured(log, "checker", EventBrief, [HumanMessage("x")], model="qwen/qwen3.8-27b")
    assert out.headline == "h"
    assert tried == ["json_schema", "json_schema", "function_calling"]


def test_openai_roles(fresh_config, monkeypatch):
    monkeypatch.setattr(fresh_config, "PROVIDER", "openai")
    monkeypatch.setattr(fresh_config, "_PREFERENCES", importlib.import_module("news2blog.config")._PREFERENCES)
    prefs = {
        "MODEL": ["gpt-4o-mini"], "RESEARCHER_MODEL": ["gpt-4o-mini"], "CHECKER_MODEL": ["gpt-4.1-mini", "gpt-4o"],
        "REPORTER_MODEL": ["gpt-4o-mini"], "JUDGE_MODEL": ["gpt-4o", "gpt-4.1"],
    }
    monkeypatch.setattr(fresh_config, "_PREFERENCES", prefs)
    monkeypatch.setattr(fresh_config, "available_models", lambda: ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"])
    m = fresh_config.resolve_models(verbose=False)
    assert m["MODEL"] == "gpt-4o-mini" and m["CHECKER_MODEL"] == "gpt-4.1-mini" and m["JUDGE_MODEL"] == "gpt-4o"
    assert fresh_config.CHECKER_FALLBACKS == ["gpt-4o"]


def test_billing_error_fails_fast():
    e = E("Error code: 429 - {'error': {'message': 'You have no credits remaining.', 'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}", 429)
    assert llm._classify(e) == "billing"
