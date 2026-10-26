"""Offline fakes: a scripted LLM and fake web tools, so the graph can be tested with no API keys."""
import json
import re
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os  # noqa: E402
os.environ["LLM_PROVIDER"] = "groq"  # tests must not depend on the developer's .env
os.environ.setdefault("TPM_LIMIT", "7500")
os.environ["MIN_WORDS"] = "0"  # the small test drafts are short on purpose; length has its own test

from news2blog import llm, tools  # noqa: E402
from news2blog.schemas import (BlogDraft, CheckerLLMOutput, ClaimVerdict, EventBrief, Expansion, JudgeOutput, NewSentence,  # noqa: E402
                               ReporterOutput, Revision, SentenceFix)

FIX = ROOT / "eval" / "fixtures" / "intel"
SOURCES = json.loads((FIX / "sources.json").read_text())
CLEAN = json.loads((FIX / "clean_draft.json").read_text())


def bad_draft() -> dict:
    d = json.loads(json.dumps(CLEAN))
    d["sections"][0]["sentences"].append(
        {"text": "Intel shares jumped 38% on the news.", "kind": "claim", "source_ids": ["S1"], "evidence": "the government will receive 433.3 million shares"})
    return d


class FakeWorld:
    def __init__(self, drafts: list[dict], stubborn: bool = False):
        self.drafts = list(drafts)
        self.stubborn = stubborn  # revisions keep re-introducing the error (to test the retry limit)
        self.calls: list[str] = []
        self.tool_steps = 0

    # --- llm.structured ---
    def structured(self, log, node, schema, messages, model=None, temperature=0.0, max_tokens=None):
        self.calls.append(f"{node}:{schema.__name__}")
        log.add_usage(node, "gpt-4o-mini", 1000, 200)
        if schema is EventBrief:
            return EventBrief(headline="US government takes 10% stake in Intel", event_date="August 22, 2025",
                              key_entities=["Intel", "Donald Trump"], search_queries=["US government Intel stake 10%"])
        if schema is BlogDraft:
            d = self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0]
            return BlogDraft(**d)
        if schema is Revision:
            refs = re.findall(r"^- \[([T\d.]+)\]", messages[-1].content, flags=re.M)
            if not self.stubborn:
                return Revision(fixes=[SentenceFix(ref=r, action="delete") for r in refs])
            return Revision(fixes=[SentenceFix(ref=r, action="replace", text="Intel shares jumped 38% on the news.",
                                               source_ids=["S1"], evidence="the government will receive 433.3 million shares")
                                   for r in refs])
        if schema is Expansion:  # adds two sourced sentences from the fixture, like a cooperative drafter
            extra = [s for sec in CLEAN["sections"] for s in sec["sentences"] if s["kind"] == "claim"][:2]
            return Expansion(new_sentences=[NewSentence(section=1, text="In detail: " + s["text"], kind="claim",
                                                        source_ids=s["source_ids"], evidence=s["evidence"]) for s in extra])
        if schema is CheckerLLMOutput:
            post = messages[-1].content.split("POST:")[-1]
            refs = re.findall(r"^\[([T\d.]+)\] \((CLAIM|OPINION)", post, flags=re.M)
            return CheckerLLMOutput(verdicts=[ClaimVerdict(ref=r, verdict="supported" if k == "CLAIM" else "not_a_claim",
                                                           supporting_source_ids=[], reason="ok") for r, k in refs])
        if schema is ReporterOutput:
            return ReporterOutput(summary="fake summary", what_each_agent_did=["Researcher: fake"], rejections=[], open_doubts=["fake doubt"])
        if schema is JudgeOutput:
            from news2blog.schemas import JudgedClaim
            return JudgeOutput(claims=[JudgedClaim(claim="433.3 million shares at $20.47", kind="fact", has_citation=True, verdict="supported", reason="S1")],
                               key_fact_contradictions=[])
        raise AssertionError(schema)

    # --- llm.tool_step: search, fetch two pages, submit ---
    def tool_step(self, log, node, messages, tool_specs, model=None, pool=None):
        self.tool_steps += 1
        log.add_usage(node, "gpt-4o-mini", 500, 50)
        step = sum(1 for m in messages if isinstance(m, AIMessage))
        if step == 0:
            return AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": "intel stake"}, "id": "t1"}])
        if step == 1:
            return AIMessage(content="", tool_calls=[{"name": "fetch_page", "args": {"url": SOURCES[1]["url"]}, "id": "t2"},
                                                     {"name": "fetch_page", "args": {"url": SOURCES[2]["url"]}, "id": "t3"}])
        return AIMessage(content="", tool_calls=[{"name": "submit_sources", "args": {"urls": [SOURCES[1]["url"], SOURCES[2]["url"]], "notes": "x"}, "id": "t4"}])


def fake_fetch(url, log=None, node="researcher"):
    for s in SOURCES:
        if s["url"] == url:
            r = {"url": url, "final_url": url, "ok": True, "title": s["title"], "date": s["date"], "text": s["text"], "error": "", "via": "fake"}
            break
    else:
        r = {"url": url, "ok": False, "title": "", "date": "", "text": "", "error": "ConnectError: name resolution failed", "via": "fake"}
    if log:
        log.event(node, "fetch", f"{'OK' if r['ok'] else 'FAIL'} {url}")
    return r


def fake_search(query, log=None, exclude_domains=None, node="researcher", **kw):
    return [{"url": s["url"], "title": s["title"], "snippet": "", "published_date": s["date"]} for s in SOURCES[1:]]


@pytest.fixture
def world(monkeypatch, tmp_path):
    def make(drafts, stubborn=False):
        w = FakeWorld(drafts, stubborn=stubborn)
        monkeypatch.setattr(llm, "structured", w.structured)
        monkeypatch.setattr(llm, "tool_step", w.tool_step)
        monkeypatch.setattr(tools, "fetch_page", fake_fetch)
        monkeypatch.setattr(tools, "search_web", fake_search)
        return w
    make.tmp = tmp_path
    return make
