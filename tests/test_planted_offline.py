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
