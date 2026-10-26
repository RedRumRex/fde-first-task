"""Agent 1: Researcher. Reads the article, then runs a tool-calling loop (search + fetch) to find 2 other sources."""
from langchain_core.runnables import RunnableConfig
import json
import re
from datetime import date
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from .. import config, llm, tools
from ..prompts import EVENT_SYSTEM, RESEARCHER_SYSTEM
from ..runlog import RunLogger
from ..schemas import EventBrief

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for news articles. Returns url, title, snippet, published_date for each hit.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch a URL and return whether it worked, its title, date and the start of its article text.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_sources",
            "description": "Finish: submit the URLs you fetched that independently cover the same event.",
            "parameters": {
                "type": "object",
                "properties": {"urls": {"type": "array", "items": {"type": "string"}}, "notes": {"type": "string"}},
                "required": ["urls", "notes"],
            },
        },
    },
]

BLOCKED = ("news.google.", "msn.com", "flipboard.", "facebook.com", "twitter.com", "x.com", "youtube.com", "reddit.com", "linkedin.com")


def tool_loop(log: RunLogger, node: str, messages: list, exclude_domains: list[str], model: str | None = None, pool: list[str] | None = None,
              allowed_urls: set[str] | None = None, enough: Callable[[dict], bool] | None = None) -> tuple[dict[str, dict], list[str], str]:
    """Let the model call search/fetch until it submits (or `enough` says we already have what we need).

    fetch_page only opens URLs that came back from search_web (or are in `allowed_urls`): models invent
    plausible-looking article URLs, and some sites redirect a bad link to an unrelated story instead of a 404.
    Returns (fetched pages by url, submitted urls, notes)."""
    allowed = set(allowed_urls or ())
    fetched: dict[str, dict] = {}
    submitted: list[str] = []
    notes = ""
    done = False
    for step in range(config.RESEARCHER_MAX_STEPS):
        ai = llm.tool_step(log, node, messages, TOOL_SPECS, model=model, pool=pool)
        messages.append(ai)
        if not ai.tool_calls:
            log.event(node, "agent_text", (ai.content or "")[:200])
            messages.append(HumanMessage("Continue using the tools. Finish by calling submit_sources."))
            continue
        for tc in ai.tool_calls:
            name, args = tc["name"], tc.get("args") or {}
            content: Any
            try:
                if name == "search_web":
                    content = tools.search_web(args.get("query", ""), log=log, exclude_domains=exclude_domains, node=node)
                    allowed.update(h["url"] for h in content if h.get("url"))
                elif name == "fetch_page":
                    url = args.get("url", "")
                    if any(b in url for b in BLOCKED):
                        content = {"ok": False, "error": "blocked domain (aggregator/social); pick an original outlet"}
                    elif url not in allowed:
                        content = {"ok": False, "error": "refused: you may only fetch URLs returned by search_web. Copy one exactly."}
                        log.event(node, "refuse_url", f"not from search results (possibly invented): {url}")
                    else:
                        r = tools.fetch_page(url, log=log, node=node)
                        fetched[url] = r
                        content = {"ok": r["ok"], "title": r["title"], "date": r["date"], "error": r["error"],
                                   "text_start": r["text"][: config.TOOL_PREVIEW_CHARS]}
                elif name == "submit_sources":
                    submitted = list(args.get("urls") or [])
                    done = True
                    notes = args.get("notes", "")
                    content = "received"
                    log.event(node, "submit", f"{len(submitted)} urls: {submitted}", urls=submitted, notes=notes)
                else:
                    content = f"unknown tool {name}"
            except Exception as e:
                content = {"error": f"{type(e).__name__}: {e}"[:300]}
                log.event(node, "tool_error", f"{name}: {content['error']}")
            messages.append(ToolMessage(content=json.dumps(content, ensure_ascii=False, default=str), tool_call_id=tc["id"]))
        if done:
            break
        if enough and enough(fetched):
            log.event(node, "auto_submit", "enough independent, on-topic sources fetched; stopping the search early")
            break
    else:
        log.event(node, "step_limit", f"hit {config.RESEARCHER_MAX_STEPS} tool steps without submitting")
    return fetched, submitted, notes


def _covers_event(page: dict, entities: list[str]) -> bool:
    """At least 2 of the event's key names appear as whole words (full name, or its last word if 4+ letters)."""
    text = (page.get("title", "") + " " + page.get("text", "")).lower()

    def found(e: str) -> bool:
        e = e.lower().strip()
        last = e.split()[-1] if e.split() else ""
        return bool(re.search(rf"\b{re.escape(e)}\b", text)) or (len(last) >= 4 and bool(re.search(rf"\b{re.escape(last)}\b", text)))

    ents = [e for e in entities if e and e.strip()]
    return sum(found(e) for e in ents) >= min(2, len(ents))


def _days_apart(a: str, b: str) -> int | None:
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


def pick_sources(log: RunLogger, node: str, primary: dict, fetched: dict, submitted: list[str], entities: list[str], n: int,
                 quiet: bool = False) -> list[dict]:
    """Deterministic guard on the agent's choice: fetched OK, different domains, mentions the event's key names,
    and (when both dates are known) published within 60 days of the primary article."""
    used = {tools.domain(primary["url"])}
    chosen: list[dict] = []
    order = [u for u in submitted if u in fetched] + [u for u in fetched if u not in submitted]
    for url in order:
        page = fetched[url]
        d = tools.domain(page.get("final_url") or url)
        reason = None
        if not page["ok"]:
            reason = "fetch failed"
        elif d in used:
            reason = f"duplicate domain {d}"
        elif not _covers_event(page, entities):
            reason = "does not mention the event's key names"
        elif (gap := _days_apart(page.get("date", ""), primary.get("date", ""))) is not None and gap > 60:
            reason = f"published {gap} days away from the original article ({page.get('date')}): probably a different story"
        if reason:
            if not quiet:
                log.event(node, "reject_source", f"{url}: {reason}")
            continue
        used.add(d)
        chosen.append(page)
        if len(chosen) == n:
            break
    return chosen


def research(log: RunLogger, url: str) -> dict:
    node = "researcher"
    primary = tools.fetch_page(url, log=log, node=node)
    if not primary["ok"]:
        log.event(node, "failed", f"could not read the input article: {primary['error']}")
        return {"research_ok": False, "research_error": f"Could not fetch the input article ({primary['error']})."}

    brief = llm.structured(
        log, node, EventBrief,
        [SystemMessage(EVENT_SYSTEM), HumanMessage(f"ARTICLE ({url}):\nTitle: {primary['title']}\nDate: {primary['date']}\n\n{primary['text'][:6000]}")],
        model=config.RESEARCHER_MODEL, max_tokens=800,
    )
    log.event(node, "event", brief.headline, brief=brief.model_dump())

    pdomain = tools.domain(primary.get("final_url") or url)
    system = RESEARCHER_SYSTEM.format(
        primary_domain=pdomain, headline=brief.headline, event_date=brief.event_date, entities=", ".join(brief.key_entities),
        n=config.NUM_EXTRA_SOURCES, queries=" | ".join(brief.search_queries), max_steps=config.RESEARCHER_MAX_STEPS,
    )
    messages = [SystemMessage(system), HumanMessage("Begin.")]
    def enough(f: dict) -> bool:
        return len(pick_sources(log, node, primary, f, [], brief.key_entities, config.NUM_EXTRA_SOURCES, quiet=True)) >= config.NUM_EXTRA_SOURCES

    fetched, submitted, notes = tool_loop(log, node, messages, exclude_domains=[pdomain], pool=[config.RESEARCHER_MODEL, config.MODEL], enough=enough)
    extra = pick_sources(log, node, primary, fetched, submitted, brief.key_entities, config.NUM_EXTRA_SOURCES)

    # Safety net: if the agent came back short, try the top results of its suggested queries directly.
    if len(extra) < config.NUM_EXTRA_SOURCES:
        log.event(node, "fallback", f"agent found {len(extra)}/{config.NUM_EXTRA_SOURCES}; trying direct search fallback")
        for q in brief.search_queries[:2]:
            try:
                hits = tools.search_web(q, log=log, exclude_domains=[pdomain], node=node)
            except Exception as e:
                log.event(node, "tool_error", str(e)[:200])
                break
            for h in hits[:4]:
                if h["url"] in fetched or any(b in h["url"] for b in BLOCKED):
                    continue
                fetched[h["url"]] = tools.fetch_page(h["url"], log=log, node=node)
            extra = pick_sources(log, node, primary, fetched, submitted, brief.key_entities, config.NUM_EXTRA_SOURCES)
            if len(extra) >= config.NUM_EXTRA_SOURCES:
                break

    sources = []
    for i, page in enumerate([primary] + extra, 1):
        sources.append({
            "id": f"S{i}", "url": page.get("final_url") or page["url"], "domain": tools.domain(page.get("final_url") or page["url"]),
            "title": page["title"], "date": page["date"], "via": page["via"], "role": "primary" if i == 1 else "corroborating",
            "text": page["text"],
        })
    log.event(node, "done", f"{len(sources)} sources: " + ", ".join(f"{s['id']}={s['domain']}" for s in sources),
              sources=[{k: v for k, v in s.items() if k != "text"} for s in sources], agent_notes=notes)
    log.save("sources.json", sources)
    return {"research_ok": True, "event": brief.model_dump(), "sources": sources}


def researcher_node(state: dict, config: RunnableConfig) -> dict:
    return research(config["configurable"]["log"], state["url"])
