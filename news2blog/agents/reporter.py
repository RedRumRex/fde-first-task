"""Agent 4: Reporter. Writes the run summary: what each agent did, what was rejected and why, cost, open doubts.
Narrative comes from the LLM; every number (cost, tokens, claim counts) is filled in by code so it can't be made up."""
from langchain_core.runnables import RunnableConfig
import json

from langchain_core.messages import HumanMessage, SystemMessage

from .. import config, llm
from ..prompts import REPORTER_SYSTEM
from ..render import render_markdown, word_count
from ..runlog import RunLogger
from ..schemas import BlogDraft, ReporterOutput

APPROVED_BANNER = "STATUS: Checker-approved DRAFT. A human editor must approve it before publishing. Nothing has been published."


def _cost_table(cost: dict) -> str:
    rows = ["| Agent | Calls | Input tokens | Output tokens | Cost (USD) |", "|---|---:|---:|---:|---:|"]
    for node, u in cost["by_node"].items():
        rows.append(f"| {node} | {u['calls']} | {u['input_tokens']:,} | {u['output_tokens']:,} | ${u['cost_usd']:.4f} |")
    rows.append(f"| **LLM total** | | {cost['input_tokens']:,} | {cost['output_tokens']:,} | **${cost['llm_usd']:.4f}** |")
    rows.append(f"| Tavily ({cost['tavily_credits']:g} credits; $0 on free tier) | | | | ${cost['tavily_usd_if_paid']:.4f} |")
    rows.append(f"| **Total per run** | | | | **${cost['total_usd']:.4f}** |")
    return "\n".join(rows)


def _attempts_table(history: list[dict]) -> str:
    rows = ["| Draft | Verdict | Claims verified | Errors | Warnings | Error types |", "|---|---|---:|---:|---:|---|"]
    for h in history:
        types = ", ".join(sorted({e["type"] for e in h["errors"]})) or "-"
        tag = " (planted error)" if h.get("planted") else (" (salvage: failing sentences cut)" if h["attempt"] > 1 + config.MAX_RETRIES else "")
        rows.append(f"| v{h['attempt']}{tag} | {'PASS' if h['passed'] else 'REJECT'} | {h['n_supported']}/{h['n_claims']} | "
                    f"{len(h['errors'])} | {len(h['warnings'])} | {types} |")
    return "\n".join(rows)


def _issue_list(history: list[dict]) -> str:
    out = []
    for h in history:
        if not h["errors"]:
            continue
        out.append(f"**Draft v{h['attempt']}**")
        for e in h["errors"]:
            out.append(f"- `[{e['ref']}]` **{e['type']}** ({e['layer']}): {e['detail']}  \n  > {e['sentence']}")
        out.append("")
    return "\n".join(out) or "_No rejections._"


def report(log: RunLogger, state: dict, use_llm: bool = True) -> dict:
    node = "reporter"
    history = state.get("history", [])
    passed = bool(history) and history[-1]["passed"]
    sources = state.get("sources", [])

    failure = state.get("failure")
    if failure:
        stage = failure.split(" crashed")[0]
        status = f"FAILED: {stage} error"
        narrative = ReporterOutput(
            summary=f"The run stopped because the {failure}. Nothing was published. Any draft below was NOT fully checked.",
            what_each_agent_did=[f"{n}: {'crashed' if n.lower() == stage else 'see log.jsonl'}" for n in ("Researcher", "Drafter", "Checker")]
                                + ["Reporter: wrote this failure report without an LLM call."],
            rejections=[], open_doubts=["Re-run after checking the error above (API limits, model availability, network)."],
        )
    elif not state.get("research_ok", False):
        status = "FAILED: research"
        narrative = ReporterOutput(
            summary=f"The run stopped at the researcher: {state.get('research_error', 'unknown error')} No draft was written and nothing was published.",
            what_each_agent_did=["Researcher: tried to fetch the input link and failed.", "Drafter: did not run.", "Checker: did not run.",
                                 "Reporter: wrote this failure report."],
            rejections=[], open_doubts=["Check that the link is correct and publicly reachable (not paywalled or blocked)."],
        )
    else:
        status = "PASSED: ready for human review" if passed else f"FAILED: checker rejected all {len(history)} drafts"
        compact = {
            "url": state["url"], "status": status, "planted_error": state.get("planted"),
            "event": state.get("event"),
            "sources": [{k: s[k] for k in ("id", "domain", "url", "title", "date", "via")} for s in sources],
            "checker_history": [{"attempt": h["attempt"], "passed": h["passed"], "errors": [{k: e[k] for k in ("ref", "type", "detail", "layer")} for e in h["errors"]],
                                 "warnings": [{k: e[k] for k in ("ref", "type", "detail")} for e in h["warnings"]]} for h in history],
        }
        narrative = None
        if use_llm:
            try:
                narrative = llm.structured(log, node, ReporterOutput,
                                           [SystemMessage(REPORTER_SYSTEM), HumanMessage(json.dumps(compact, indent=1, ensure_ascii=False))],
                                           model=config.REPORTER_MODEL, max_tokens=1500)
            except Exception as e:  # the report must still be written
                log.event(node, "llm_failed", f"narrative unavailable ({str(e)[:150]}); writing tables only")
        if narrative is None:
            narrative = ReporterOutput(summary=status, what_each_agent_did=[], rejections=[], open_doubts=[])

    # never let the narrative say "no rejections" when the log shows some: rebuild that list from the facts
    rejected = [h for h in history if not h["passed"]]
    if rejected and not narrative.rejections:
        narrative.rejections = [
            f"Draft v{h['attempt']}{' (planted error)' if h.get('planted') else ''}: "
            + "; ".join(f"[{e['ref']}] {e['type']} ({e['layer']})" for e in h["errors"])
            + (" -> fixed in the next draft" if any(x["attempt"] == h["attempt"] + 1 for x in history) else "")
            for h in rejected]

    final_name = None
    if state.get("draft"):
        draft = BlogDraft(**state["draft"])
        if passed:
            final_name = "final_post.md"
            log.save(final_name, render_markdown(draft, sources, banner=APPROVED_BANNER))
        else:
            final_name = "final_post_REJECTED.md"
            banner = (f"STATUS: NOT CHECKED, the run failed ({failure}). Do NOT publish." if failure else
                      f"STATUS: REJECTED by the checker after {len(history)} drafts. Do NOT publish. See report.md.")
            log.save(final_name, render_markdown(draft, sources, banner=banner))

    log.event(node, "done", status)
    cost = log.cost_summary()
    log.save("cost.json", cost)

    md = [f"# Run report: {state['url']}", "",
          f"- **Run ID:** `{log.run_id}`", f"- **Status:** {status}",
          f"- **Drafts written:** {len(history)} (max {1 + config.MAX_RETRIES})",
          f"- **Models:** researcher `{config.RESEARCHER_MODEL}` (+ `{config.MODEL}` when rate-limited), drafter `{config.MODEL}`, checker `{config.CHECKER_MODEL}`",
          f"- **Cost:** ${cost['total_usd']:.4f} · **Time:** {cost['duration_s']}s"]
    if state.get("planted"):
        p = state["planted"]
        caught = bool(history) and not history[0]["passed"] and any(e["ref"] == p["ref"] for e in history[0]["errors"])
        md.append(f"- **Planted error:** {p['description']} → **{'CAUGHT' if caught else 'MISSED'}** by the checker")
    if state.get("draft") and history:
        last = history[-1]
        md.append(f"- **Final draft:** {word_count(BlogDraft(**state['draft']))} words, {last['n_supported']}/{last['n_claims']} claims verified, "
                  f"{len(sources)} sources")
    md += ["", "## Summary", "", narrative.summary, "",
           "## What each agent did", ""] + [f"- {x}" for x in narrative.what_each_agent_did] + [""]
    if sources:
        md += ["## Sources used", ""] + [f"- **{s['id']}** [{s['title'] or s['domain']}]({s['url']}) ({s['domain']}, fetched via {s['via']})" for s in sources] + [""]
    if history:
        md += ["## Checker verdicts per draft", "", _attempts_table(history), "",
               "## What was rejected and why", ""] + ([f"- {x}" for x in narrative.rejections] or ["_No rejections._"]) + ["",
               "<details><summary>Every flagged claim (raw)</summary>", "", _issue_list(history), "</details>", ""]
    conflicts = [w for w in (history[-1]["warnings"] if history else []) if w["type"] == "sources_disagree"]
    if state.get("salvaged"):
        md += ["## Sentences cut by the salvage step", "",
               f"After {1 + config.MAX_RETRIES} drafts these sentences still could not be verified, so they were removed and the "
               "shortened post was re-checked in full:", ""] + [f"- ~~{s}~~" for s in state["salvaged"]] + [""]
    md += ["## Cost", "", _cost_table(cost), "", "## Open doubts for the editor", ""] + [f"- {x}" for x in narrative.open_doubts]
    if conflicts:
        md += ["", "**Sources disagree (the post follows its cited source; the editor should pick):**", ""] + \
              [f"- `[{w['ref']}]` {w['detail']}  \n  > {w['sentence']}" for w in conflicts]
    md += [""]
    md += ["## Files", "", "- `log.jsonl`: every agent action, in order", "- `sources.json`: fetched source text",
           "- `draft_vN.md/json`, `check_vN.json`: each draft and its checker verdict",
           f"- `{final_name or '(no post)'}`: the output", "- `cost.json`: token and cost breakdown", ""]
    report_md = "\n".join(md)
    log.save("report.md", report_md)
    return {"status": status, "report_md": report_md, "final_post_file": final_name}


def reporter_node(state: dict, config: RunnableConfig) -> dict:
    return report(config["configurable"]["log"], state)
