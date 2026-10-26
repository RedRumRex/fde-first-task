"""Error planting, used to prove the checker works. Each function takes a draft and returns
(mutated draft, ref of the planted sentence, human description)."""
from langchain_core.runnables import RunnableConfig
import re

from ..schemas import BlogDraft, Sentence
from ..verify import _DM_RE, _MD_RE, iter_sentences
from ..runlog import RunLogger


def _first_claim(draft: BlogDraft) -> tuple[int, int, Sentence]:
    for i, sec in enumerate(draft.sections):
        for j, s in enumerate(sec.sentences):
            if s.kind == "claim" and s.source_ids:
                return i, j, s
    return 0, 0, Sentence(text="", kind="claim", source_ids=["S1"], evidence="")


def plant_invented_stat(draft: BlogDraft) -> tuple[BlogDraft, str, str]:
    """A made-up statistic that LOOKS sourced: it cites S-ids and reuses a real evidence quote."""
    d = draft.model_copy(deep=True)
    i, j, base = _first_claim(d)
    fake = Sentence(
        text="Analysts estimate the move will lift revenue by 47% within two years.",
        kind="claim", source_ids=list(base.source_ids) or ["S1"], evidence=base.evidence,
    )
    d.sections[i].sentences.insert(j + 1, fake)
    return d, f"{i + 1}.{j + 2}", f"Invented statistic with a real-looking citation: \"{fake.text}\""


def _shift_day(day: int) -> int:
    return day + 3 if day <= 25 else day - 3


def plant_wrong_date(draft: BlogDraft) -> tuple[BlogDraft, str, str]:
    """Change the day in the first dated claim (e.g. 'August 26' -> 'August 29'). Falls back to the year."""
    d = draft.model_copy(deep=True)
    for ref, s in iter_sentences(d):
        if ref == "T" or s.kind != "claim":
            continue
        for rx, day_group in ((_MD_RE, 2), (_DM_RE, 1)):
            m = rx.search(s.text)
            if m:
                old = m.group(0)
                day = int(m.group(day_group))
                new = old.replace(str(day), str(_shift_day(day)), 1)
                s.text = s.text.replace(old, new, 1)
                return d, ref, f"Wrong date: changed '{old}' to '{new}' in [{ref}]"
    for ref, s in iter_sentences(d):
        if ref == "T" or s.kind != "claim":
            continue
        m = re.search(r"\b(20\d\d)\b", s.text)
        if m:
            old = m.group(1)
            new = str(int(old) - 1)
            s.text = s.text.replace(old, new, 1)
            return d, ref, f"Wrong date: changed year '{old}' to '{new}' in [{ref}]"
    # no date anywhere: insert one that no source contains
    i, j, base = _first_claim(d)
    d.sections[i].sentences.insert(j + 1, Sentence(text="The news was first announced on March 3.", kind="claim",
                                                   source_ids=list(base.source_ids) or ["S1"], evidence=base.evidence))
    return d, f"{i + 1}.{j + 2}", "Wrong date: inserted 'The news was first announced on March 3.'"


def plant_uncited_claim(draft: BlogDraft) -> tuple[BlogDraft, str, str]:
    """A factual claim with no source at all."""
    d = draft.model_copy(deep=True)
    sec = d.sections[-1]
    fake = Sentence(text="The company's chief executive has already said he will step down once the deal closes.",
                    kind="claim", source_ids=[], evidence="")
    sec.sentences.insert(0, fake)
    return d, f"{len(d.sections)}.1", f"Uncited claim: \"{fake.text}\""


def plant_disguised_fact(draft: BlogDraft) -> tuple[BlogDraft, str, str]:
    """Bonus: an uncited fact labelled as 'opinion' and containing no digits, so only the LLM layer can catch it."""
    d = draft.model_copy(deep=True)
    sec = d.sections[-1]
    fake = Sentence(text="Regulators in Europe have already opened a formal investigation into the deal.", kind="opinion")
    sec.sentences.append(fake)
    return d, f"{len(d.sections)}.{len(sec.sentences)}", f"Fact disguised as opinion: \"{fake.text}\""


PLANTS = {
    "stat": plant_invented_stat,
    "date": plant_wrong_date,
    "uncited": plant_uncited_claim,
    "disguised": plant_disguised_fact,
}


def plant_node(state: dict, config: RunnableConfig) -> dict:
    log: RunLogger = config["configurable"]["log"]
    from ..render import render_markdown

    draft, ref, desc = PLANTS[state["plant"]](BlogDraft(**state["draft"]))
    log.event("plant_error", "planted", f"[{ref}] {desc}", ref=ref, plant=state["plant"])
    log.save("draft_v1_planted.md", render_markdown(draft, state["sources"]))
    return {"draft": draft.model_dump(), "planted": {"type": state["plant"], "ref": ref, "description": desc}}
