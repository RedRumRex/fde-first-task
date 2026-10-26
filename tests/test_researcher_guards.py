"""Regression tests for the failure seen in the first live Groq run: the researcher invented an NBC URL
(".../rcna123456"), NBC redirected it to an unrelated 2023 panda story, and it slipped in as source S2."""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from news2blog import llm, tools
from news2blog.agents.researcher import pick_sources, tool_loop
from news2blog.runlog import RunLogger

from conftest import SOURCES

PRIMARY = {**SOURCES[0], "ok": True, "final_url": SOURCES[0]["url"]}
PANDA = {"url": "https://www.nbcnews.com/news/us-news/u-s-takes-10-stake-intel-rcna123456", "ok": True, "via": "httpx",
         "title": "With return of three pandas to China, U.S. could soon have none", "date": "2023-11-05",
         "text": "HONG KONG - Some of the last giant pandas in the United States are heading back to China. "
                 "Trending: Intelligence officials, Trump rally, and more. " * 5}


def test_invented_url_is_refused(monkeypatch, tmp_path):
    log = RunLogger(base=tmp_path, quiet=True)
    calls = iter([
        AIMessage(content="", tool_calls=[{"name": "fetch_page", "args": {"url": PANDA["url"]}, "id": "a"}]),
        AIMessage(content="", tool_calls=[{"name": "submit_sources", "args": {"urls": [], "notes": ""}, "id": "b"}]),
    ])
    monkeypatch.setattr(llm, "tool_step", lambda *a, **k: next(calls))
    fetched_urls = []
    monkeypatch.setattr(tools, "fetch_page", lambda url, **k: fetched_urls.append(url) or PANDA)
    fetched, _, _ = tool_loop(log, "researcher", [SystemMessage("x"), HumanMessage("go")], exclude_domains=[])
    assert fetched_urls == [] and fetched == {}
    assert "refuse_url" in (log.dir / "log.jsonl").read_text()


def test_off_topic_redirect_is_rejected(tmp_path):
    log = RunLogger(base=tmp_path, quiet=True)
    good = {**SOURCES[1], "ok": True}
    chosen = pick_sources(log, "researcher", PRIMARY, {PANDA["url"]: PANDA, good["url"]: good}, [PANDA["url"]],
                          ["Intel", "Donald Trump", "CHIPS Act"], n=2)
    assert [c["url"] for c in chosen] == [good["url"]]
    assert "probably a different story" in (log.dir / "log.jsonl").read_text() or "key names" in (log.dir / "log.jsonl").read_text()


def test_whole_word_entity_match(tmp_path):
    log = RunLogger(base=tmp_path, quiet=True)
    page = {**PANDA, "date": ""}  # even with no date to compare, "Intelligence" must not count as "Intel"
    assert pick_sources(log, "researcher", PRIMARY, {page["url"]: page}, [], ["Intel", "CHIPS Act"], n=1) == []
