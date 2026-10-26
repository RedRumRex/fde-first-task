"""The 3 required planted errors must be caught by the deterministic layer alone; the clean control must pass."""
import pytest

from news2blog.agents.checker import check_draft
from news2blog.agents.plant import PLANTS
from news2blog.runlog import RunLogger
from news2blog.schemas import BlogDraft

from conftest import CLEAN, SOURCES


@pytest.fixture
def log(tmp_path):
    return RunLogger(base=tmp_path, quiet=True)


def test_clean_control_passes(log):
    res = check_draft(log, BlogDraft(**CLEAN), SOURCES, use_llm=False)
    assert res.passed, [i.model_dump() for i in res.errors()]


@pytest.mark.parametrize("plant,expected_type", [
    ("stat", "number_not_in_source"),
    ("date", "date_not_in_source"),
    ("uncited", "missing_citation"),
])
def test_planted_error_caught(log, plant, expected_type):
    draft, ref, _ = PLANTS[plant](BlogDraft(**CLEAN))
    res = check_draft(log, draft, SOURCES, use_llm=False)
    assert not res.passed
    flagged = {(i.ref, i.type) for i in res.errors()}
    assert (ref, expected_type) in flagged, flagged


def test_disguised_fact_needs_llm_layer(log):
    draft, ref, _ = PLANTS["disguised"](BlogDraft(**CLEAN))
    res = check_draft(log, draft, SOURCES, use_llm=False)
    assert res.passed  # no digits, labelled opinion: deterministic layer can't see it; LLM layer must


def test_opinion_may_repeat_a_cited_figure_but_not_add_one(log):
    """Live run: 'The warrant for an extra 5%...' (5% cited two sentences earlier) was rejected 3 times."""
    from news2blog.schemas import Sentence
    d = BlogDraft(**CLEAN)
    d.sections[-1].sentences.append(Sentence(text="The extra 5% warrant gives the government a lever if things change.", kind="opinion"))
    assert check_draft(log, d, SOURCES, use_llm=False).passed
    d.sections[-1].sentences.append(Sentence(text="Expect a 40% stake within a decade.", kind="opinion"))
    res = check_draft(log, d, SOURCES, use_llm=False)
    assert not res.passed and {i.type for i in res.errors()} == {"uncited_fact_in_opinion"}


def test_off_by_one_year_is_caught(log):
    """Planted-error run on the real draft: '2022' -> '2021' slipped through a 0.1% number tolerance."""
    from news2blog.schemas import Sentence
    d = BlogDraft(**CLEAN)
    s = d.sections[0].sentences[0]
    d.sections[0].sentences[0] = Sentence(text=s.text.replace("2025", "2024"), kind="claim", source_ids=s.source_ids, evidence=s.evidence)
    res = check_draft(log, d, SOURCES, use_llm=False)
    assert not res.passed and ("1.1", "number_not_in_source") in {(i.ref, i.type) for i in res.errors()}


def test_wrong_year_that_appears_elsewhere_in_source_is_caught(log):
    """Eval c05: 'On September 2, 2024, Judge Mehta ruled...' slipped through because '2024' appears in the source
    in an unrelated sentence ('found in August 2024'). Sources were published in 2025."""
    from news2blog.schemas import Sentence
    srcs = [dict(s) for s in SOURCES]
    srcs[0]["text"] += " In August 2024 a court found something unrelated."
    d = BlogDraft(**CLEAN)
    s = d.sections[0].sentences[0]
    d.sections[0].sentences[0] = Sentence(text="On August 22, 2024, the US government said it will take a 10% stake in Intel.",
                                          kind="claim", source_ids=["S1"], evidence=s.evidence)
    res = check_draft(log, d, srcs, use_llm=False)
    assert ("1.1", "date_not_in_source") in {(i.ref, i.type) for i in res.errors()}
    ok = BlogDraft(**CLEAN)  # the correct "August 22, 2025" still passes
    assert check_draft(log, ok, srcs, use_llm=False).passed


def test_citation_repair_ignores_unrelated_mentions():
    """The repair must not 'fix' a citation using a number that only appears in an unrelated sentence."""
    from news2blog.schemas import Sentence
    from news2blog.verify import repair_citations
    srcs = [dict(s) for s in SOURCES]
    srcs[2]["text"] += " Separately, a football club sold 77 tickets."
    d = BlogDraft(**CLEAN)
    d.sections[0].sentences[1] = Sentence(text="The government will receive 77 million Intel shares.", kind="claim",
                                          source_ids=["S1"], evidence="the government will receive 433.3 million shares")
    repair_citations(d, srcs)
    assert d.sections[0].sentences[1].source_ids == ["S1"]


def test_wrong_year_when_source_omits_the_year(log):
    """The exact c05 shape: source says 'on Sept. 2' (no year), published 2025; post says 'September 2, 2024'."""
    from news2blog.schemas import Sentence
    srcs = [dict(s) for s in SOURCES]
    srcs[0]["text"] += " The deal was signed on Sept. 2 after talks. In 2024 the firm reported losses."
    d = BlogDraft(**CLEAN)
    d.sections[0].sentences.append(Sentence(text="The deal was signed on September 2, 2024.", kind="claim",
                                            source_ids=["S1"], evidence="The deal was signed on Sept. 2 after talks."))
    assert ("1.4", "date_not_in_source") in {(i.ref, i.type) for i in check_draft(log, d, srcs, use_llm=False).errors()}
    d.sections[0].sentences[-1].text = "The deal was signed on September 2, 2025."
    assert check_draft(log, d, srcs, use_llm=False).passed
