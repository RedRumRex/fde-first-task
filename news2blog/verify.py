"""Deterministic layer of the checker: no LLM, so it cannot be talked into accepting an invented number.

For every claim sentence it verifies:
  * the claim has at least one citation and the cited IDs exist
  * every digit-written number in the claim appears in a cited source (unit-aware: $1.5bn == 1,500,000,000)
  * every month-day date in the claim appears in a cited source
  * the evidence quote really is in the cited source (word 5-gram overlap)
Opinion sentences must not carry numbers or dates (that would be an uncited fact in disguise).
"""
import re
from typing import Iterator

from .schemas import BlogDraft, Issue, Sentence

WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "dozen": 12,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "half": 50,
}
SCALES = {
    "thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "tn": 1e12, "t": 1e12, "crore": 1e7, "lakh": 1e5,
}
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion|crore|lakh|mn|bn|tn|k|m|b|t)\b)?", re.I)
_MD_RE = re.compile(_MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_DM_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_RE + r"\b", re.I)
_ISO_RE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
# "September 2, 2025" / "Sept. 2 2025" / "2 September 2025"
_MDY_RE = re.compile(_MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
_DMY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_RE + r",?\s+(20\d\d)\b", re.I)
_STOP = set("that this with from have will were been their they which about after into over than also more most said says what when where while would could should there these those under other only some such".split())


def normalize(s: str) -> str:
    s = s.lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


# ---------------- numbers ----------------
def claim_numbers(text: str) -> list[tuple[str, set[float]]]:
    """Digit-written numbers in a claim, each with its possible values (raw and unit-scaled)."""
    out = []
    for m in _NUM_RE.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        v = float(raw.replace(",", ""))
        vals = {v}
        if unit in SCALES:
            vals.add(v * SCALES[unit])
        out.append((m.group(0).strip(), vals))
    return out


def source_numbers(text: str) -> set[float]:
    vals: set[float] = set()
    for m in _NUM_RE.finditer(text):
        v = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        vals.add(v)
        if unit in SCALES:
            vals.add(v * SCALES[unit])
        if v >= 1e5:  # 1,500,000,000 also matches "1.5 billion"
            for s in (1e3, 1e5, 1e6, 1e7, 1e9, 1e12):
                vals.add(round(v / s, 3))
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in WORD_NUMS:
            vals.add(float(WORD_NUMS[w]))
    return vals


def _num_in(vals: set[float], pool: set[float]) -> bool:
    for v in vals:
        for p in pool:
            # exact match (float noise only): a 0.1% tolerance once let "2021" pass for "2022"
            if v == p or (p and abs(v - p) / abs(p) < 1e-9):
                return True
    return False


# ---------------- dates ----------------
def _month(name: str) -> int:
    return MONTHS[name.lower()[:3]]


def month_days(text: str) -> set[tuple[int, int]]:
    out = set()
    for m in _MD_RE.finditer(text):
        d = int(m.group(2))
        if 1 <= d <= 31:
            out.add((_month(m.group(1)), d))
    for m in _DM_RE.finditer(text):
        d = int(m.group(1))
        if 1 <= d <= 31:
            out.add((_month(m.group(2)), d))
    return out


def source_month_days(text: str) -> set[tuple[int, int]]:
    out = month_days(text)
    for m in _ISO_RE.finditer(text):
        out.add((int(m.group(2)), int(m.group(3))))
    return out


def full_dates(text: str) -> set[tuple[int, int, int]]:
    out = set()
    for m in _MDY_RE.finditer(text):
        out.add((_month(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _DMY_RE.finditer(text):
        out.add((_month(m.group(2)), int(m.group(1)), int(m.group(3))))
    for m in _ISO_RE.finditer(text):
        out.add((int(m.group(2)), int(m.group(3)), int(m.group(1))))
    return out


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in _STOP}


def cooccurs(claim: str, source_text: str, needle: str | None = None, vals: set[float] | None = None, md=None,
             min_overlap: float = 0.3) -> bool:
    """Does the source mention this figure/date in a sentence that is ABOUT the same thing as the claim?
    (A '2024' in an unrelated sentence must not count as support.)"""
    cw = _content_words(claim)
    if not cw:
        return True
    for sent in re.split(r"(?<=[.!?])\s+", source_text):
        hit = (vals is not None and _num_in(vals, source_numbers(sent))) or (md is not None and md in source_month_days(sent))
        if hit and len(cw & _content_words(sent)) / len(cw) >= min_overlap:
            return True
    return False


# ---------------- evidence ----------------
def evidence_overlap(evidence: str, source_text: str, n: int = 5) -> float:
    ev = re.findall(r"\w+", normalize(evidence))
    if not ev:
        return 0.0
    src_norm = " ".join(re.findall(r"\w+", normalize(source_text)))
    if " ".join(ev) in src_norm:
        return 1.0
    if len(ev) < n:
        return 1.0 if " ".join(ev) in src_norm else 0.0
    grams = [" ".join(ev[i:i + n]) for i in range(len(ev) - n + 1)]
    return sum(1 for g in grams if g in src_norm) / len(grams)


# ---------------- iteration ----------------
def iter_sentences(draft: BlogDraft) -> Iterator[tuple[str, Sentence]]:
    """Yield (ref, sentence). The title is ref 'T' and is always treated as a claim."""
    yield "T", Sentence(text=draft.title, kind="claim", source_ids=draft.title_source_ids, evidence="")
    for i, sec in enumerate(draft.sections, 1):
        for j, s in enumerate(sec.sentences, 1):
            yield f"{i}.{j}", s


def deterministic_check(draft: BlogDraft, sources: list[dict]) -> list[Issue]:
    by_id = {s["id"]: s for s in sources}
    all_nums = {sid: source_numbers(s["text"]) for sid, s in by_id.items()}
    all_dates = {sid: source_month_days(s["text"]) for sid, s in by_id.items()}
    issues: list[Issue] = []
    # figures/dates already stated by a cited claim in this post: an opinion may refer back to them
    cited_vals: set[float] = set()
    cited_dates: set[tuple[int, int]] = set()
    for ref, s in iter_sentences(draft):
        if s.kind == "claim" and s.source_ids:
            for _, vals in claim_numbers(_DM_RE.sub(" ", _MD_RE.sub(" ", s.text))):
                cited_vals |= vals
            cited_dates |= month_days(s.text)

    def add(ref, s, typ, sev, detail):
        issues.append(Issue(ref=ref, sentence=s.text, type=typ, severity=sev, detail=detail, layer="deterministic"))

    for ref, s in iter_sentences(draft):
        dates = month_days(s.text)
        # day numbers inside "August 26" are checked as dates, not again as bare numbers
        nums = claim_numbers(_DM_RE.sub(" ", _MD_RE.sub(" ", s.text)))
        if s.kind == "opinion":
            new = [n for n, vals in nums if not (vals & cited_vals)] + [f"{m}/{d}" for m, d in dates if (m, d) not in cited_dates]
            if new:
                add(ref, s, "uncited_fact_in_opinion", "error",
                    f"Opinion sentence introduces figures/dates {new} that no cited claim in the post states.")
            continue

        cited = [sid for sid in s.source_ids if sid in by_id]
        bad = [sid for sid in s.source_ids if sid not in by_id]
        if bad:
            add(ref, s, "bad_source_id", "error", f"Cites unknown source IDs {bad}.")
        if not cited:
            add(ref, s, "missing_citation", "error", "Factual claim has no source URL.")
            continue

        cited_nums = set().union(*(all_nums[c] for c in cited))
        other_nums = set().union(*(all_nums[c] for c in by_id if c not in cited)) if len(by_id) > len(cited) else set()
        for raw, vals in nums:
            if _num_in(vals, cited_nums):
                continue
            if _num_in(vals, other_nums):
                where = [c for c in by_id if c not in cited and _num_in(vals, all_nums[c])]
                add(ref, s, "wrong_citation", "error", f"Number '{raw}' is not in cited {cited} but appears in {where}; cite the right source.")
            else:
                add(ref, s, "number_not_in_source", "error", f"Number '{raw}' does not appear in any source.")

        cited_dates = set().union(*(all_dates[c] for c in cited))
        any_dates = set().union(*all_dates.values())
        for md in dates:
            if md in cited_dates:
                continue
            label = f"{['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][md[0]]} {md[1]}"
            if md in any_dates:
                add(ref, s, "wrong_citation", "error", f"Date '{label}' is not in cited {cited} but appears in another source.")
            else:
                add(ref, s, "date_not_in_source", "error", f"Date '{label}' does not appear in any source.")

        # a full date ("September 2, 2024") whose exact form no cited source contains must at least carry the
        # year the cited sources were published in: catches a wrong year that happens to appear elsewhere in a source
        cited_full = set().union(*(full_dates(by_id[c]["text"]) for c in cited))
        pub_years = {int(by_id[c]["date"][:4]) for c in cited if str(by_id[c].get("date", ""))[:4].isdigit()}
        cited_md = set().union(*(all_dates[c] for c in cited))
        for (mo, dy, yr) in full_dates(s.text):
            if (mo, dy, yr) in cited_full:
                continue
            other_years = sorted({y for (m, d, y) in cited_full if (m, d) == (mo, dy)})
            if other_years:
                add(ref, s, "date_not_in_source", "error",
                    f"Year {yr} is wrong: the cited source gives this date as {other_years}.")
            elif pub_years and (mo, dy) in cited_md and yr not in pub_years:
                add(ref, s, "date_not_in_source", "error",
                    f"The source gives this date without a year and was published in {sorted(pub_years)}, not {yr}: likely a wrong year.")
            elif pub_years and yr not in pub_years and (yr + 1) not in pub_years:
                add(ref, s, "date_not_in_source", "error",
                    f"Full date with year {yr} is not in the cited sources (published {sorted(pub_years)}): likely a wrong year.")

        if ref != "T":
            if not s.evidence.strip():
                add(ref, s, "evidence_missing", "warning", "No evidence quote given.")
            else:
                best = max(evidence_overlap(s.evidence, by_id[c]["text"]) for c in cited)
                if best < 0.3:
                    add(ref, s, "evidence_not_in_source", "error", f"Evidence quote not found in cited source (overlap {best:.0%}).")
                elif best < 0.6:
                    add(ref, s, "evidence_not_in_source", "warning", f"Evidence quote only loosely matches the cited source (overlap {best:.0%}).")
    return issues


def repair_citations(draft: BlogDraft, sources: list[dict]) -> list[str]:
    """Code-only fix for wrong citations: if a number/date in a claim is missing from the cited sources but present in
    another source, add that source's ID. Never removes citations, never changes text. Returns a log of changes."""
    by_id = {s["id"]: s for s in sources}
    nums = {sid: source_numbers(s["text"]) for sid, s in by_id.items()}
    dates = {sid: source_month_days(s["text"]) for sid, s in by_id.items()}
    changes = []
    for ref, s in iter_sentences(draft):
        if ref == "T" or s.kind != "claim" or not s.source_ids:
            continue
        cited = [c for c in s.source_ids if c in by_id]
        if not cited:
            continue
        add: list[str] = []
        for _, vals in claim_numbers(_DM_RE.sub(" ", _MD_RE.sub(" ", s.text))):
            if any(_num_in(vals, nums[c]) for c in cited):
                continue
            add += [o for o in by_id if o not in cited and o not in add and _num_in(vals, nums[o])
                    and cooccurs(s.text, by_id[o]["text"], vals=vals)][:1]
        for md in month_days(s.text):
            if any(md in dates[c] for c in cited):
                continue
            add += [o for o in by_id if o not in cited and o not in add and md in dates[o]
                    and cooccurs(s.text, by_id[o]["text"], md=md)][:1]
        if add:
            s.source_ids = list(s.source_ids) + add
            changes.append(f"[{ref}] +{add}")
    return changes
