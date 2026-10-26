"""Agent 2: Drafter. Writes the post in the tone guide; on rejection, revises using the checker's issues."""
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, SystemMessage

from .. import config, llm
from ..prompts import DRAFTER_PATCH, DRAFTER_REVISE, DRAFTER_SYSTEM, DRAFTER_USER
from ..render import numbered_view, render_markdown, word_count
from ..runlog import RunLogger
from ..schemas import BlogDraft, Revision, Section, Sentence
from ..verify import repair_citations


def format_sources(sources: list[dict]) -> str:
    return "\n\n".join(
        f"[{s['id']}] {s['title']} ({s['domain']}, {s.get('date') or 'date unknown'})\nURL: {s['url']}\n{s['text']}" for s in sources
    )


def tone_guide() -> str:
    try:
        return config.TONE_GUIDE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "Clear, plain, neutral."


FIX_HINTS = {
    "number_not_in_source": "Use the exact figure from the sources, or delete the sentence.",
    "date_not_in_source": "Use the exact date a source gives, or remove the date (or delete the sentence).",
    "wrong_citation": "Keep the text but change source_ids to the source(s) that actually contain the detail.",
    "missing_citation": "Add the source_ids that state this, or delete the sentence if no source does.",
    "bad_source_id": "Only use the source IDs listed in SOURCES.",
    "evidence_not_in_source": "Replace evidence with a quote copied character-for-character from the first cited source.",
    "uncited_fact_in_opinion": "Remove the figure/date from this opinion sentence (keep it purely analytical), or delete it.",
    "unsupported": "No source states this. Delete the sentence.",
    "contradicted": "Rewrite it to say exactly what the source says (see detail), or delete it.",
    "partial": "Remove the detail the sources don't state (see detail), keeping only what they do state.",
    "post_too_thin": "Write a fuller post: more well-supported factual claims from the sources.",
}


def apply_fixes(prev: BlogDraft, rev: Revision, flagged: set[str], log: RunLogger, node: str) -> BlogDraft:
    """Merge sentence-level fixes into the previous draft. Unflagged sentences are untouchable; a flagged sentence the
    model didn't address is deleted (it was wrong, so leaving it would just fail again)."""
    fixes = {f.ref.strip("[] "): f for f in rev.fixes if f.ref.strip("[] ") in flagged}
    d = prev.model_copy(deep=True)
    if "T" in fixes and fixes["T"].action == "replace" and fixes["T"].text.strip():
        d.title, d.title_source_ids = fixes["T"].text.strip(), fixes["T"].source_ids or d.title_source_ids
    new_sections = []
    for i, sec in enumerate(d.sections, 1):
        kept = []
        for j, s in enumerate(sec.sentences, 1):
            ref = f"{i}.{j}"
            if ref not in flagged:
                kept.append(s)
                continue
            f = fixes.get(ref)
            if f and f.action == "replace" and f.text.strip():
                kept.append(Sentence(text=f.text.strip(), kind=f.kind, source_ids=f.source_ids, evidence=f.evidence))
        if kept:
            new_sections.append(Section(heading=sec.heading, sentences=kept))
    d.sections = new_sections
    done = {r: (fixes[r].action if r in fixes else "deleted (no fix given)") for r in sorted(flagged)}
    log.event(node, "patch", ", ".join(f"[{r}] {a}" for r, a in done.items()), fixes=done)
    return d


def write_draft(log: RunLogger, sources: list[dict], headline: str, attempt: int,
                prev: BlogDraft | None = None, issues: list[dict] | None = None, node: str = "drafter") -> BlogDraft:
    msgs = [
        SystemMessage(DRAFTER_SYSTEM.format(tone_guide=tone_guide())),
        HumanMessage(DRAFTER_USER.format(sources=format_sources(sources), headline=headline)),
    ]
    if prev is not None and issues:
        issue_lines = "\n".join(
            f"- [{i['ref']}] \"{i['sentence']}\"\n    PROBLEM ({i['type']}): {i['detail']}\n    FIX: {FIX_HINTS.get(i['type'], 'Fix it or delete the sentence.')}"
            for i in issues)
        flagged = {i["ref"] for i in issues if i["ref"] != "post"}
        if any(i["type"] == "post_too_thin" for i in issues) or not flagged:
            # the post as a whole is the problem: full rewrite
            msgs.append(HumanMessage(DRAFTER_REVISE.format(attempt=attempt - 1, numbered=numbered_view(prev, evidence=False), issues=issue_lines)))
            draft = llm.structured(log, node, BlogDraft, msgs, temperature=0.3, max_tokens=2500)
        else:
            # surgical: only flagged sentences may change, so a retry cannot break what already passed
            msgs.append(HumanMessage(DRAFTER_PATCH.format(attempt=attempt - 1, numbered=numbered_view(prev, evidence=False), issues=issue_lines)))
            rev = llm.structured(log, node, Revision, msgs, temperature=0.2, max_tokens=1500)
            draft = apply_fixes(prev, rev, flagged, log, node)
    else:
        draft = llm.structured(log, node, BlogDraft, msgs, temperature=0.4, max_tokens=2500)
    fixed = repair_citations(draft, sources)
    if fixed:
        log.event(node, "cite_repair", f"code added the source that actually contains the figure/date: {', '.join(fixed)}")
    log.save(f"draft_v{attempt}.json", draft.model_dump())
    log.save(f"draft_v{attempt}.md", render_markdown(draft, sources))
    n_claims = sum(1 for sec in draft.sections for s in sec.sentences if s.kind == "claim")
    log.event(node, "draft" if prev is None else "revision",
              f"v{attempt}: '{draft.title}' ({word_count(draft)} words, {n_claims} claims)", attempt=attempt)
    return draft


def drafter_node(state: dict, config: RunnableConfig) -> dict:
    log: RunLogger = config["configurable"]["log"]
    attempt = state.get("attempt", 0) + 1
    prev = BlogDraft(**state["draft"]) if state.get("draft") and attempt > 1 else None
    issues = state.get("check", {}).get("errors") if prev else None
    draft = write_draft(log, state["sources"], state["event"]["headline"], attempt, prev, issues)
    return {"draft": draft.model_dump(), "attempt": attempt}
