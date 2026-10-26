"""Agent 3: Checker. A separate agent with its own prompt. Two layers:
  1. deterministic: citations exist, numbers/dates/evidence really appear in the cited source text
  2. LLM: claim-by-claim verdict against the full sources
Any error from either layer rejects the draft."""
import re

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, SystemMessage

from .. import config, llm
from ..prompts import CHECKER_SYSTEM
from ..render import numbered_view, word_count
from ..runlog import RunLogger
from ..schemas import BlogDraft, CheckerLLMOutput, CheckResult, Issue
from ..verify import deterministic_check, iter_sentences


def _sources_block(sources: list[dict]) -> str:
    return "\n\n".join(f"=== {s['id']} ({s['domain']}) ===\n{s['text']}" for s in sources)


def _norm_ref(r: str) -> str:
    """'[1.1]', 'Sentence 1.1', ' 1.1 ', 'title' -> '1.1' / 'T'."""
    s = str(r).strip().upper()
    if s in ("TITLE", "HEADLINE", "[T]"):
        return "T"
    m = re.search(r"\b(T|\d+\.\d+)\b", s)
    return m.group(1) if m else s


def llm_check(log: RunLogger, draft: BlogDraft, sources: list[dict], node: str = "checker") -> CheckerLLMOutput:
    """Get a verdict for EVERY claim. Missing verdicts are re-asked, then handed to a backup model.
    If some claims still have no verdict, raise: a post must never pass with claims nobody checked."""
    base = [SystemMessage(CHECKER_SYSTEM), HumanMessage(f"SOURCES:\n{_sources_block(sources)}\n\nPOST:\n{numbered_view(draft)}")]
    claim_refs = [ref for ref, _ in iter_sentences(draft)]  # every sentence, opinions included
    models = [config.CHECKER_MODEL] + [m for m in config.CHECKER_FALLBACKS if m != config.CHECKER_MODEL]
    verdicts: dict = {}
    violations: list[str] = []
    for mi, model in enumerate(models):
        missing = [r for r in claim_refs if r not in verdicts]
        if not missing:
            break
        if mi > 0:
            log.event(node, "fallback_model", f"{len(missing)} claims still unchecked; asking backup checker {model}")
        msgs = list(base) + ([HumanMessage(f"Give verdicts ONLY for these refs, one verdict per ref: {missing}")] if verdicts else [])
        for attempt in range(2):  # first ask + one re-ask on the same model
            try:
                out = llm.structured(log, node, CheckerLLMOutput, msgs, model=model, max_tokens=1800)
            except llm.LLMError as e:
                log.event(node, "model_failed", f"{model}: {str(e)[:150]}")
                break
            for v in out.verdicts:
                v.ref = _norm_ref(v.ref)
                if v.ref in claim_refs and v.ref not in verdicts:
                    verdicts[v.ref] = v
            violations += [_norm_ref(x) for x in out.opinion_violations]
            missing = [r for r in claim_refs if r not in verdicts]
            if not missing:
                break
            log.event(node, "recheck", f"{model} gave no verdict for {missing}; asking again")
            msgs = list(base) + [HumanMessage(f"You gave no verdict for these refs: {missing}. "
                                              f"Return a verdict for EACH of them, using exactly these ref strings.")]
    missing = [r for r in claim_refs if r not in verdicts]
    if missing:
        raise llm.LLMError(f"checker could not get a verdict for {len(missing)}/{len(claim_refs)} claims {missing} "
                           f"from {models}; refusing to pass unchecked claims")
    return CheckerLLMOutput(verdicts=list(verdicts.values()), opinion_violations=sorted(set(violations)))


def check_draft(log: RunLogger, draft: BlogDraft, sources: list[dict], use_llm: bool = True, node: str = "checker") -> CheckResult:
    sentences = dict(iter_sentences(draft))
    issues: list[Issue] = deterministic_check(draft, sources)
    supported_refs: set[str] = set()

    if use_llm:
        out = llm_check(log, draft, sources, node)
        verdicts = {v.ref: v for v in out.verdicts}
        for ref, s in sentences.items():
            v = verdicts.get(ref)
            if s.kind == "opinion":
                # a "fact disguised as opinion": the LLM says it asserts something checkable that no source supports
                if (v and v.verdict in ("not_found", "contradicted", "partially_supported")) or ref in out.opinion_violations:
                    issues.append(Issue(ref=ref, sentence=s.text, type="uncited_fact_in_opinion", severity="error",
                                        detail=f"Labelled opinion but asserts a fact no source supports. {v.reason if v else ''}".strip(),
                                        layer="llm"))
                continue
            if v is None:
                issues.append(Issue(ref=ref, sentence=s.text, type="unchecked", severity="error", detail="Checker returned no verdict.", layer="llm"))
                continue
            if v.verdict == "sources_disagree":
                # the drafter matched a cited source; the sources themselves conflict -> an open doubt for the editor
                supported_refs.add(ref)
                issues.append(Issue(ref=ref, sentence=s.text, type="sources_disagree", severity="warning",
                                    detail=v.reason, layer="llm"))
                continue
            if v.verdict in ("supported", "not_a_claim"):
                supported_refs.add(ref)
                cited = set(s.source_ids)
                if v.verdict == "supported" and v.supporting_source_ids and cited and not cited & set(v.supporting_source_ids):
                    issues.append(Issue(ref=ref, sentence=s.text, type="wrong_citation", severity="warning",
                                        detail=f"Supported by {v.supporting_source_ids}, but cites {sorted(cited)}.", layer="llm"))
            else:
                typ = {"not_found": "unsupported", "contradicted": "contradicted", "partially_supported": "partial"}[v.verdict]
                issues.append(Issue(ref=ref, sentence=s.text, type=typ, severity="error", detail=v.reason, layer="llm"))
    else:
        supported_refs = {r for r, s in sentences.items() if s.kind == "claim"}

    if use_llm:
        # the evidence quote is an audit aid: if the LLM read the full sources and found the claim supported,
        # a paraphrased quote is a warning, not a reason to reject
        for i in issues:
            if i.type == "evidence_not_in_source" and i.severity == "error" and i.ref in supported_refs:
                i.severity = "warning"
                i.detail += " (claim itself verified by the LLM layer, so not blocking)"

    # a post with (almost) no facts must never pass, however clean it is
    body_claims = [r for r, s in sentences.items() if s.kind == "claim" and r != "T"]
    if len(body_claims) < config.MIN_CLAIMS:
        issues.append(Issue(ref="post", sentence="(whole post)", type="post_too_thin", severity="error", layer="deterministic",
                            detail=f"Only {len(body_claims)} factual claims; a post needs at least {config.MIN_CLAIMS}."))

    # gpt-4o-mini under-writes word targets (eval drafts: 144-331 words), so length is enforced in code
    words = word_count(draft)
    if words < config.MIN_WORDS:
        issues.append(Issue(ref="post", sentence="(whole post)", type="post_too_short", severity="error", layer="deterministic",
                            detail=f"Only {words} words; a post needs at least {config.MIN_WORDS}."))

    error_refs = {i.ref for i in issues if i.severity == "error"}
    claim_refs = [r for r, s in sentences.items() if s.kind == "claim"]
    return CheckResult(
        passed=not error_refs,
        n_claims=len(claim_refs),
        n_supported=len([r for r in claim_refs if r in supported_refs and r not in error_refs]),
        issues=issues,
    )


def checker_node(state: dict, config: RunnableConfig) -> dict:
    log: RunLogger = config["configurable"]["log"]
    attempt = state["attempt"]
    draft = BlogDraft(**state["draft"])
    result = check_draft(log, draft, state["sources"])
    log.save(f"check_v{attempt}.json", result.model_dump())
    errors = result.errors()
    for i in errors:
        log.event("checker", "flag", f"[{i.ref}] {i.type} ({i.layer}): {i.detail[:160]}", ref=i.ref, type=i.type, layer=i.layer)
    verdict = "PASS" if result.passed else "REJECT"
    log.event("checker", verdict.lower(), f"v{attempt}: {verdict} - {result.n_supported}/{result.n_claims} claims verified, "
              f"{len(errors)} errors, {len(result.issues) - len(errors)} warnings", attempt=attempt, passed=result.passed)
    entry = {"attempt": attempt, "passed": result.passed, "n_claims": result.n_claims, "n_supported": result.n_supported,
             "errors": [i.model_dump() for i in errors], "warnings": [i.model_dump() for i in result.issues if i.severity == "warning"],
             "planted": bool(state.get("plant")) and attempt == 1}
    return {"check": entry, "history": [entry]}
