"""Structured outputs exchanged between agents."""
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Researcher ----------
class EventBrief(BaseModel):
    """What the primary article is about, used to search for corroborating coverage."""

    headline: str = Field(description="One-line neutral description of the news event")
    event_date: str = Field(description="Date the event happened as stated in the article, or 'unknown'")
    key_entities: list[str] = Field(description="3-6 names (companies, people, products, places) central to the event")
    search_queries: list[str] = Field(description="2-3 web search queries that would find OTHER outlets covering this same event")


class SourcePick(BaseModel):
    urls: list[str] = Field(description="Exactly the URLs you fetched and judged to cover the same event")
    notes: str = Field(description="One or two sentences on why these are independent coverage of the same event")


# ---------- Drafter ----------
class Sentence(BaseModel):
    text: str = Field(description="One sentence of the post, exactly as it will appear (no citation markers)")
    kind: Literal["claim", "opinion"] = Field(
        description="'claim' = states a fact (number, date, name, event, quote). "
        "'opinion' = the blog's own analysis/framing that introduces NO new facts."
    )
    source_ids: list[str] = Field(default_factory=list, description="IDs like S1, S2 that support this claim. Required for claims.")
    evidence: str = Field(
        default="",
        description="For claims: a short VERBATIM quote (max ~40 words) copied from the first cited source that supports the claim.",
    )


class Section(BaseModel):
    heading: str
    sentences: list[Sentence]


class BlogDraft(BaseModel):
    title: str = Field(description="Headline, under 12 words. Must be supported by the sources.")
    title_source_ids: list[str] = Field(default_factory=list, description="Source IDs supporting the headline")
    sections: list[Section]


# ---------- Drafter revision (patch) ----------
class SentenceFix(BaseModel):
    ref: str = Field(description="The flagged ref you are fixing, e.g. '2.3' or 'T' for the headline")
    action: Literal["replace", "delete"] = Field(description="replace = corrected sentence below; delete = remove it")
    text: str = Field(default="", description="For replace: the corrected sentence, supported by the sources")
    kind: Literal["claim", "opinion"] = "claim"
    source_ids: list[str] = Field(default_factory=list)
    evidence: str = Field(default="", description="For replace claims: verbatim quote copied from the first cited source")


class Revision(BaseModel):
    fixes: list[SentenceFix] = Field(description="Exactly one fix per flagged ref")


# ---------- Checker ----------
class ClaimVerdict(BaseModel):
    ref: str = Field(description="The sentence reference, e.g. 'T' for title or '2.3' for section 2 sentence 3")
    verdict: Literal["supported", "partially_supported", "not_found", "contradicted", "not_a_claim"]
    supporting_source_ids: list[str] = Field(default_factory=list, description="Which sources actually support it (may differ from the cited ones)")
    reason: str = Field(description="Short justification. For problems, say exactly which detail is wrong or missing and what the source says instead.")


class CheckerLLMOutput(BaseModel):
    verdicts: list[ClaimVerdict]
    opinion_violations: list[str] = Field(
        default_factory=list,
        description="Refs of sentences labelled 'opinion' that actually assert facts (numbers, dates, events, quotes) without a source",
    )


class Issue(BaseModel):
    ref: str
    sentence: str
    type: str  # missing_citation | bad_source_id | number_not_in_source | date_not_in_source | evidence_not_in_source | unsupported | contradicted | uncited_fact_in_opinion | wrong_citation | partial
    severity: Literal["error", "warning"]
    detail: str
    layer: Literal["deterministic", "llm"]


class CheckResult(BaseModel):
    passed: bool
    n_claims: int
    n_supported: int
    issues: list[Issue]

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]


# ---------- Reporter ----------
class ReporterOutput(BaseModel):
    summary: str = Field(description="2-3 sentences: outcome of the run and whether the post is ready for human review")
    what_each_agent_did: list[str] = Field(description="One bullet per agent (Researcher, Drafter, Checker, Reporter) describing what it did in this run")
    rejections: list[str] = Field(description="One bullet per checker rejection: which claims failed, why, and how the next draft fixed it. Empty if none.")
    open_doubts: list[str] = Field(description="Things the human editor should double-check before publishing")


# ---------- Eval judge ----------
class JudgedClaim(BaseModel):
    claim: str = Field(description="One atomic statement from the post, as written")
    kind: Literal["fact", "interpretation"] = Field(
        description="fact = checkable (a number, date, name, event, who did/said what). interpretation = analysis, meaning, "
                    "significance or a hedged prediction (\"this signals...\", \"validates...\", \"could reshape...\").")
    has_citation: bool = Field(description="True if the sentence containing it carries a citation link")
    verdict: Literal["supported", "unsupported", "contradicted"]
    reason: str


class JudgeOutput(BaseModel):
    claims: list[JudgedClaim]
    key_fact_contradictions: list[str] = Field(
        default_factory=list, description="Any reference key fact that the post states differently (wrong number/date/name)"
    )
