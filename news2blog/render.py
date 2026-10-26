"""Turn a structured BlogDraft into markdown with an inline source URL on every claim."""
from .schemas import BlogDraft
from .verify import iter_sentences


def _cites(ids: list[str], sources: list[dict]) -> str:
    idx = {s["id"]: (n, s["url"]) for n, s in enumerate(sources, 1)}
    return "".join(f" [[{idx[i][0]}]]({idx[i][1]})" for i in ids if i in idx)


def render_markdown(draft: BlogDraft, sources: list[dict], banner: str | None = None) -> str:
    lines = []
    if banner:
        lines += [f"> {banner}", ""]
    lines += [f"# {draft.title}{_cites(draft.title_source_ids, sources)}", ""]
    for sec in draft.sections:
        lines += [f"## {sec.heading}", ""]
        para = []
        for s in sec.sentences:
            text = s.text.strip()
            cites = _cites(s.source_ids, sources) if s.kind == "claim" else ""
            if cites and text[-1:] in ".!?":
                text = text[:-1] + cites + text[-1]  # "...in Intel [[1]](url)."
            else:
                text += cites
            para.append(text)
        lines += [" ".join(para), ""]
    lines += ["---", "", "**Sources**", ""]
    for n, s in enumerate(sources, 1):
        title = (s.get("title") or s["url"]).replace("[", "(").replace("]", ")")
        lines.append(f"{n}. [{title}]({s['url']}) ({s.get('domain', '')})")
    return "\n".join(lines) + "\n"


def numbered_view(draft: BlogDraft, evidence: bool = True) -> str:
    """Compact view with refs, used in prompts for the checker and the drafter's revision."""
    out = []
    for ref, s in iter_sentences(draft):
        tag = "OPINION" if s.kind == "opinion" else f"CLAIM cites={s.source_ids}"
        ev = f'\n      evidence: "{s.evidence}"' if evidence and s.kind == "claim" and s.evidence else ""
        out.append(f"[{ref}] ({tag}) {s.text}{ev}")
    return "\n".join(out)


def word_count(draft: BlogDraft) -> int:
    return sum(len(s.text.split()) for sec in draft.sections for s in sec.sentences)
