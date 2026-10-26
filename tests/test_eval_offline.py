"""The eval harness itself: scoring rules, scoreboard and demo.md auto-fill, with fakes."""
from eval import run_eval

from conftest import CLEAN, SOURCES, bad_draft


def test_eval_scoring_and_demo_fill(world, tmp_path, monkeypatch):
    world([CLEAN])
    demo = tmp_path / "demo.md"
    demo.write_text("intro\n<!-- SCORES:START -->\nold\n<!-- SCORES:END -->\noutro\n")
    monkeypatch.setattr(run_eval, "DEMO", demo)
    case = {"id": "c01", "url": SOURCES[0]["url"], "key_facts": ["x"]}
    dead = {"id": "c14_dead_link", "url": "https://nope.example/x", "expect_failure": True}
    (tmp_path / "judge").mkdir()
    rows = [run_eval.run_case(case, "day2", tmp_path), run_eval.run_case(dead, "day2", tmp_path),
            run_eval.run_case(case, "day1", tmp_path)]
    assert rows[0]["passed"] and rows[0]["shipped"] and not rows[0]["bad_shipped"]
    assert rows[1]["passed"] and rows[1]["note"] == "failed cleanly"
    assert rows[2]["passed"]
    summ = [run_eval.summarize(rows, "day1"), run_eval.summarize(rows, "day2")]
    assert summ[1]["passed"] == 2 and summ[1]["cases"] == 2
    sb = run_eval.scoreboard(summ, rows, "now")
    assert "Day 2: 4 roles + checker" in sb
    run_eval.update_demo(summ, "now")
    txt = demo.read_text()
    assert "old" not in txt and "| Cases passed | 1/1 | 2/2 |" in txt and txt.endswith("outro\n")


def test_withheld_post_is_not_a_pass(world, tmp_path):
    world([bad_draft()], stubborn=True)
    (tmp_path / "judge").mkdir()
    rec = run_eval.run_case({"id": "c01", "url": SOURCES[0]["url"], "key_facts": []}, "day2", tmp_path)
    assert rec["status"].startswith("FAILED") and not rec["shipped"] and not rec["passed"] and not rec["bad_shipped"]


def test_rejudge_rescores_finished_jobs(world, tmp_path):
    world([CLEAN])
    (tmp_path / "judge").mkdir()
    case = {"id": "c01", "url": SOURCES[0]["url"], "key_facts": []}
    rec = run_eval.run_case(case, "day2", tmp_path)
    rec.update(passed=False, problems=["stale"])  # pretend an old judge failed it
    [new] = run_eval.rejudge([rec], [case], tmp_path)
    assert new["passed"] and "problems" in new and new["problems"] == []
