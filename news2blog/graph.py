"""Day 2 system: the four roles as a LangGraph with an explicit checker -> drafter retry loop.

    START -> researcher -> drafter -> [plant_error] -> checker --pass--> reporter -> END
                 |                                       |
                 +--(research failed)--> reporter        +--reject & drafts left--> drafter
                                                         +--reject & no drafts left--> reporter (FAILED)
"""
import functools
import operator
import traceback
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from . import config
from .agents.checker import checker_node
from .agents.drafter import drafter_node
from .agents.plant import plant_node
from .agents.reporter import reporter_node
from .agents.researcher import researcher_node
from .runlog import RunLogger


class State(TypedDict, total=False):
    url: str
    plant: Optional[str]
    research_ok: bool
    research_error: str
    event: dict
    sources: list[dict]
    draft: dict
    attempt: int
    check: dict
    history: Annotated[list[dict], operator.add]
    planted: dict
    status: str
    report_md: str
    final_post_file: Optional[str]
    failure: str  # set when an agent crashed; the run goes straight to the reporter
    salvaged: list  # sentences removed by the last-resort salvage step


def safe(name: str, fn):
    """Wrap a node so an exception (API outage, model failure) ends the run with a report instead of a traceback."""
    @functools.wraps(fn)
    def wrapper(state: dict, config: RunnableConfig) -> dict:
        try:
            return fn(state, config)
        except Exception as e:  # noqa: BLE001
            log = config["configurable"]["log"]
            msg = f"{name} crashed: {type(e).__name__}: {str(e)[:300]}"
            log.event(name, "crash", msg, trace=traceback.format_exc()[-2000:])
            return {"failure": msg}
    return wrapper


def after_research(state: State) -> str:
    return "drafter" if state.get("research_ok") and not state.get("failure") else "reporter"


def after_draft(state: State) -> str:
    if state.get("failure"):
        return "reporter"
    return "plant_error" if state.get("plant") and state["attempt"] == 1 else "checker"


def after_check(state: State) -> str:
    if state.get("failure"):
        return "reporter"
    if state["check"]["passed"]:
        return "reporter"
    if state["attempt"] >= 1 + config.MAX_RETRIES:
        if can_salvage(state):
            return "salvage"
        return "reporter"  # out of retries: report the failure, don't loop forever
    return "drafter"


MAX_SALVAGE = 3


def can_salvage(state: State) -> bool:
    """Out of drafts: if only a few individual sentences still fail, we can cut them instead of withholding the post."""
    if state.get("salvaged") is not None:
        return False  # one salvage only
    errors = state["check"]["errors"]
    refs = {e["ref"] for e in errors}
    return bool(refs) and "post" not in refs and "T" not in refs and len(refs) <= MAX_SALVAGE


def salvage_node(state: State, config: RunnableConfig) -> dict:
    """Remove the sentences that still fail after the last draft, then send the post back to the full checker.
    Deleting an unverified sentence can't add an error; the re-check (incl. the 4-fact minimum) decides if it ships."""
    from .agents.drafter import apply_fixes
    from .render import render_markdown
    from .schemas import BlogDraft, Revision

    log = config["configurable"]["log"]
    errors = state["check"]["errors"]
    refs = sorted({e["ref"] for e in errors})
    prev = BlogDraft(**state["draft"])
    sentences = {e["ref"]: e["sentence"] for e in errors}
    draft = apply_fixes(prev, Revision(fixes=[]), set(refs), log, "salvage")
    attempt = state["attempt"] + 1
    log.event("salvage", "cut", f"removed {len(refs)} unverifiable sentence(s) {refs}; re-checking v{attempt}",
              removed=[sentences[r] for r in refs])
    log.save(f"draft_v{attempt}.json", draft.model_dump())
    log.save(f"draft_v{attempt}.md", render_markdown(draft, state["sources"]))
    return {"draft": draft.model_dump(), "attempt": attempt, "salvaged": [sentences[r] for r in refs]}


def build_graph():
    g = StateGraph(State)
    g.add_node("researcher", safe("researcher", researcher_node))
    g.add_node("drafter", safe("drafter", drafter_node))
    g.add_node("plant_error", plant_node)
    g.add_node("checker", safe("checker", checker_node))
    g.add_node("salvage", safe("salvage", salvage_node))
    g.add_node("reporter", reporter_node)
    g.add_edge(START, "researcher")
    g.add_conditional_edges("researcher", after_research, ["drafter", "reporter"])
    g.add_conditional_edges("drafter", after_draft, ["plant_error", "checker", "reporter"])
    g.add_edge("plant_error", "checker")
    g.add_conditional_edges("checker", after_check, ["drafter", "salvage", "reporter"])
    g.add_edge("salvage", "checker")
    g.add_edge("reporter", END)
    return g.compile()


def run_pipeline(url: str, plant: str | None = None, quiet: bool = False, run_id: str | None = None, base=None) -> dict[str, Any]:
    log = RunLogger(run_id=run_id, base=base, quiet=quiet)
    log.event("pipeline", "start", f"url={url} plant={plant} model={config.MODEL} max_drafts={1 + config.MAX_RETRIES}", url=url, plant=plant)
    final = build_graph().invoke({"url": url, "plant": plant, "history": []},
                                 config={"configurable": {"log": log}, "recursion_limit": 40})
    final["run_dir"] = str(log.dir)
    final["cost"] = log.cost_summary()
    return final
