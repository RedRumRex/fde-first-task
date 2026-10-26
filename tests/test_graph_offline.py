"""End-to-end graph tests with a fake LLM and fake web: routing, retry limit, failure reporting, planting."""
import json
from pathlib import Path

from news2blog import config
from news2blog.graph import run_pipeline

from conftest import CLEAN, SOURCES, bad_draft


def test_rejects_then_passes(world):
    world([bad_draft(), CLEAN])
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    assert out["status"].startswith("PASSED")
    assert [h["passed"] for h in out["history"]] == [False, True]
    assert any(e["type"] == "number_not_in_source" for e in out["history"][0]["errors"])
    d = Path(out["run_dir"])
    for f in ["log.jsonl", "report.md", "final_post.md", "cost.json", "sources.json", "draft_v1.md", "check_v1.json", "draft_v2.md"]:
        assert (d / f).exists(), f
    assert "Checker-approved DRAFT" in (d / "final_post.md").read_text()
    assert out["cost"]["llm_usd"] > 0
    assert len(out["sources"]) == 3 and len({s["domain"] for s in out["sources"]}) == 3


def test_stops_after_max_retries(world):
    world([bad_draft()], stubborn=True)
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    assert out["status"].startswith("FAILED")
    assert len(out["history"]) == 1 + config.MAX_RETRIES
    assert (Path(out["run_dir"]) / "final_post_REJECTED.md").exists()
    assert not (Path(out["run_dir"]) / "final_post.md").exists()


def test_dead_link_fails_cleanly(world):
    world([CLEAN])
    out = run_pipeline("https://does-not-exist.example/x", quiet=True, base=world.tmp)
    assert out["status"] == "FAILED: research"
    assert not out.get("draft")
    assert "FAILED" in (Path(out["run_dir"]) / "report.md").read_text()


def test_planted_stat_caught_live_then_fixed(world):
    world([CLEAN])
    out = run_pipeline(SOURCES[0]["url"], plant="stat", quiet=True, base=world.tmp)
    first = out["history"][0]
    assert first["planted"] and not first["passed"]
    assert out["planted"]["ref"] in {e["ref"] for e in first["errors"]}
    assert out["status"].startswith("PASSED")
    assert "CAUGHT" in (Path(out["run_dir"]) / "report.md").read_text()
    events = [json.loads(l) for l in (Path(out["run_dir"]) / "log.jsonl").read_text().splitlines()]
    assert [e["node"] for e in events if e["kind"] == "planted"] == ["plant_error"]


def test_checker_falls_back_to_backup_model(world, monkeypatch):
    """Live failure: qwen produced invalid JSON 3 times. The checker must switch model, not crash."""
    from news2blog import llm
    w = world([CLEAN])
    real = w.structured

    def flaky(log, node, schema, messages, model=None, **kw):
        if node == "checker" and model == config.CHECKER_MODEL:
            raise llm.LLMError("checker: qwen failed to return valid CheckerLLMOutput after 3 attempts")
        return real(log, node, schema, messages, model=model, **kw)

    monkeypatch.setattr(llm, "structured", flaky)
    monkeypatch.setattr(config, "CHECKER_FALLBACKS", ["qwen/qwen3.8-27b"])
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    assert out["status"].startswith("PASSED")
    assert "fallback_model" in (Path(out["run_dir"]) / "log.jsonl").read_text()


def test_crash_becomes_a_clean_failure_report(world, monkeypatch):
    from news2blog import llm
    w = world([CLEAN])
    real = w.structured

    def broken(log, node, schema, messages, **kw):
        if node == "checker":
            raise llm.LLMError("all checker models down")
        return real(log, node, schema, messages, **kw)

    monkeypatch.setattr(llm, "structured", broken)
    monkeypatch.setattr(config, "CHECKER_FALLBACKS", [])
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    assert out["status"] == "FAILED: checker error"
    d = Path(out["run_dir"])
    assert "NOT CHECKED" in (d / "final_post_REJECTED.md").read_text()
    assert not (d / "final_post.md").exists()
    assert "checker crashed" in (d / "report.md").read_text()


def test_never_passes_with_unchecked_claims(world, monkeypatch):
    """Live failure: qwen returned empty verdict lists and v2 PASSED with 9/11 claims never checked."""
    from news2blog import llm
    from news2blog.schemas import CheckerLLMOutput
    w = world([CLEAN])
    real = w.structured

    def lazy(log, node, schema, messages, **kw):
        if schema is CheckerLLMOutput:
            return CheckerLLMOutput(verdicts=[], opinion_violations=[])  # returns nothing, every time, every model
        return real(log, node, schema, messages, **kw)

    monkeypatch.setattr(llm, "structured", lazy)
    monkeypatch.setattr(config, "CHECKER_FALLBACKS", ["qwen/qwen3.8-27b"])
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    assert out["status"] == "FAILED: checker error"
    assert not (Path(out["run_dir"]) / "final_post.md").exists()
    assert "refusing to pass unchecked claims" in (Path(out["run_dir"]) / "report.md").read_text()


def test_messy_refs_are_matched():
    from news2blog.agents.checker import _norm_ref
    assert [_norm_ref(r) for r in ["[1.1]", "Sentence 2.3", " 4.2 ", "title", "[T]", "T"]] == ["1.1", "2.3", "4.2", "T", "T", "T"]


def test_report_lists_rejections_even_if_llm_forgets(world):
    """Live run: the reporter LLM returned no rejections although v1 was rejected; the report said 'No rejections'."""
    world([CLEAN])
    out = run_pipeline(SOURCES[0]["url"], plant="date", quiet=True, base=world.tmp)
    rep = (Path(out["run_dir"]) / "report.md").read_text()
    section = rep.split("## What was rejected and why")[1].split("<details>")[0]
    assert "No rejections" not in section and "Draft v1 (planted error)" in section and "fixed in the next draft" in section


def test_llm_catches_fact_disguised_as_opinion(world, monkeypatch, tmp_path):
    """Bonus plant missed in the live suite: the checker now gives every OPINION sentence a verdict too."""
    from news2blog import llm
    from news2blog.agents.checker import check_draft
    from news2blog.agents.plant import PLANTS
    from news2blog.runlog import RunLogger
    from news2blog.schemas import BlogDraft, CheckerLLMOutput, ClaimVerdict
    from news2blog.verify import iter_sentences
    draft, ref, _ = PLANTS["disguised"](BlogDraft(**CLEAN))

    def checker_llm(log, node, schema, messages, **kw):
        return CheckerLLMOutput(verdicts=[ClaimVerdict(ref=r, verdict=("not_found" if r == ref else "supported" if s.kind == "claim" else "not_a_claim"),
                                                       reason="Regulators: no source mentions an investigation" if r == ref else "ok")
                                          for r, s in iter_sentences(draft)])
    monkeypatch.setattr(llm, "structured", checker_llm)
    res = check_draft(RunLogger(base=tmp_path, quiet=True), draft, SOURCES)
    assert not res.passed and (ref, "uncited_fact_in_opinion") in {(i.ref, i.type) for i in res.errors()}


def test_revision_only_touches_flagged_sentences(world):
    """Live eval: full rewrites added new errors and once deleted every fact. Patches can't touch unflagged sentences."""
    world([bad_draft()])
    out = run_pipeline(SOURCES[0]["url"], quiet=True, base=world.tmp)
    v1 = json.loads((Path(out["run_dir"]) / "draft_v1.json").read_text())
    v2 = json.loads((Path(out["run_dir"]) / "draft_v2.json").read_text())
    flat = lambda d: [s["text"] for sec in d["sections"] for s in sec["sentences"]]
    assert flat(v2) == [t for t in flat(v1) if "38%" not in t]  # only the flagged sentence went; everything else identical
    assert out["status"].startswith("PASSED")


def test_post_with_no_facts_never_passes(tmp_path):
    """Live eval c01: the drafter deleted every factual sentence and a facts-free post PASSED."""
    from news2blog.agents.checker import check_draft
    from news2blog.runlog import RunLogger
    from news2blog.schemas import BlogDraft
    d = BlogDraft(**CLEAN)
    d.sections = [d.sections[-1]]  # only "Why it matters" left: 2 claims + 1 opinion
    res = check_draft(RunLogger(base=tmp_path, quiet=True), d, SOURCES, use_llm=False)
    assert not res.passed and any(i.type == "post_too_thin" for i in res.errors())
