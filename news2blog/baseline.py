"""Day 1 system: ONE agent, end to end. Same tools, same writing rules, same model, but no separate checker and no retries.
It is the yardstick the four-role graph has to beat."""
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from . import config, llm, tools
from .agents.drafter import format_sources, tone_guide
from .agents.researcher import tool_loop
from .prompts import BASELINE_SYSTEM, DRAFTER_SYSTEM, DRAFTER_USER
from .render import render_markdown, word_count
from .runlog import RunLogger
from .schemas import BlogDraft


def run_baseline(url: str, quiet: bool = False, run_id: str | None = None, base=None) -> dict[str, Any]:
    log = RunLogger(run_id=run_id, base=base, quiet=quiet)
    node = "single_agent"
    log.event("pipeline", "start", f"DAY-1 BASELINE url={url} model={config.MODEL}", url=url)
    system = BASELINE_SYSTEM.format(n=config.NUM_EXTRA_SOURCES) + "\n\n" + DRAFTER_SYSTEM.format(tone_guide=tone_guide())
    messages = [SystemMessage(system), HumanMessage(f"News link: {url}")]
    def enough(f: dict) -> bool:  # the input page + N other domains fetched OK (no relevance guard: that's Day 2's job)
        doms = {tools.domain(p.get("final_url") or u) for u, p in f.items() if p["ok"]}
        return url in f and len(doms - {tools.domain(url)}) >= config.NUM_EXTRA_SOURCES

    fetched, submitted, _ = tool_loop(log, node, messages, exclude_domains=[tools.domain(url)], allowed_urls={url}, enough=enough)

    primary = fetched.get(url) or tools.fetch_page(url, log=log, node=node)
    if not primary["ok"]:
        log.event(node, "failed", f"could not read the input article: {primary['error']}")
        log.save("cost.json", log.cost_summary())
        return {"status": "FAILED: research", "research_ok": False, "run_dir": str(log.dir), "cost": log.cost_summary()}

    # No checker, no guard rails: take what the agent fetched, one page per domain
    pages, seen = [primary], {tools.domain(primary.get("final_url") or url)}
    for u in submitted + list(fetched):
        p = fetched.get(u)
        if p and p["ok"] and tools.domain(p.get("final_url") or u) not in seen:
            seen.add(tools.domain(p.get("final_url") or u))
            pages.append(p)
    sources = [{"id": f"S{i}", "url": p.get("final_url") or p["url"], "domain": tools.domain(p.get("final_url") or p["url"]),
                "title": p["title"], "date": p["date"], "via": p["via"], "text": p["text"]} for i, p in enumerate(pages[:3], 1)]
    log.save("sources.json", sources)

    messages.append(HumanMessage(DRAFTER_USER.format(sources=format_sources(sources), headline=sources[0]["title"])))
    draft = llm.structured(log, node, BlogDraft, messages, temperature=0.4, max_tokens=2500)
    log.save("draft_v1.json", draft.model_dump())
    md = render_markdown(draft, sources, banner="STATUS: Day-1 single-agent draft (no checker).")
    log.save("final_post.md", md)
    log.event(node, "draft", f"'{draft.title}' ({word_count(draft)} words)")
    cost = log.cost_summary()
    log.save("cost.json", cost)
    return {"status": "DONE (unchecked)", "research_ok": True, "sources": sources, "draft": draft.model_dump(),
            "run_dir": str(log.dir), "cost": cost, "final_post_file": "final_post.md"}
