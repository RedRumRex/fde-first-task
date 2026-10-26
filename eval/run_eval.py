"""Score the system on the test set: Day 1 (single agent) vs Day 2 (four roles + checker).

  python -m eval.run_eval                       # both modes, all 14 cases
  python -m eval.run_eval --modes day2 --cases c01_intel_stake,c04_nvidia_5t
  python -m eval.run_eval --workers 4

Each post is graded by an INDEPENDENT judge (different prompt, different model family: JUDGE_MODEL),
never by the pipeline's own checker, so the system is not grading itself.

A case PASSES when the system ships a post AND every factual claim has a source URL AND the judge finds no unsupported or
contradicted claim AND no human-verified key fact is contradicted. Day 2 runs that the checker rejects are "withheld":
not a pass, but not a bad post shipped either. The negative (dead-link) case passes if the system fails cleanly.
"""
import argparse
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from news2blog import config, llm
from news2blog.baseline import run_baseline
from news2blog.graph import run_pipeline
from news2blog.prompts import JUDGE_SYSTEM
from news2blog.runlog import RunLogger
from news2blog.schemas import JudgeOutput

ROOT = Path(__file__).resolve().parent
DEMO = ROOT.parent / "demo.md"


def judge(post_md: str, sources: list[dict], key_facts: list[str], log: RunLogger) -> JudgeOutput:
    body = post_md.split("\n---\n")[0]
    src = "\n\n".join(f"=== Source {i} ({s['domain']}) {s['url']} ===\n{s['text'][:9000]}" for i, s in enumerate(sources, 1))
    facts = "\n".join(f"- {k}" for k in key_facts) or "(none)"
    msgs = [SystemMessage(JUDGE_SYSTEM), HumanMessage(f"SOURCES:\n{src}\n\nKEY FACTS:\n{facts}\n\nPOST:\n{body}")]
    backups = [m for m in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b") if m not in (config.JUDGE_MODEL, config.CHECKER_MODEL)]
    for model in [config.JUDGE_MODEL] + backups:
        try:
            out = llm.structured(log, "judge", JudgeOutput, msgs, model=model, max_tokens=2500)
        except llm.LLMError as e:
            log.event("judge", "model_failed", f"{model}: {str(e)[:150]}")
            continue
        if out.claims:  # an empty grading would silently score the case as a fail
            return out
        log.event("judge", "empty", f"{model} returned no claims; trying the next judge model")
    raise llm.LLMError("no judge model returned a usable grading")


def run_case(case: dict, mode: str, out_dir: Path) -> dict:
    run_id = f"{mode}-{case['id']}"
    base = out_dir / "runs"
    rec = {"case": case["id"], "mode": mode, "url": case["url"]}
    try:
        out = run_baseline(case["url"], quiet=True, run_id=run_id, base=base) if mode == "day1" else \
            run_pipeline(case["url"], quiet=True, run_id=run_id, base=base)
    except Exception as e:
        rec.update(status=f"CRASH: {type(e).__name__}: {e}", shipped=False, passed=False, error=traceback.format_exc()[-1500:])
        return rec
    rec.update(status=out.get("status"), cost_usd=out["cost"]["total_usd"], duration_s=out["cost"]["duration_s"],
               drafts=len(out.get("history") or []) or (1 if out.get("draft") else 0))
    shipped = out.get("status", "").startswith(("PASSED", "DONE"))
    rec["shipped"] = shipped

    if case.get("expect_failure"):
        rec["passed"] = not shipped and not out.get("draft")
        rec["note"] = "failed cleanly" if rec["passed"] else "should have failed"
        return rec
    if not out.get("final_post_file"):
        rec["passed"] = False
        return rec

    if not shipped:  # withheld by the checker: not a pass, not a bad post shipped; skip the judge to save tokens
        rec.update(passed=False, bad_shipped=False, note="withheld by checker (not judged)")
        return rec
    return score_post(rec, Path(out["run_dir"]) / out["final_post_file"], out["sources"], case, out_dir)


def score_post(rec: dict, post_path: Path, sources: list[dict], case: dict, out_dir: Path) -> dict:
    """Judge one shipped post and fill in the scoring fields of `rec`."""
    run_id = f"{rec['mode']}-{rec['case']}"
    jlog = RunLogger(run_id=run_id + "-judge", base=out_dir / "judge", quiet=True)
    try:
        j = judge(post_path.read_text(), sources, case.get("key_facts", []), jlog)
    except Exception as e:
        rec.update(passed=False, error=f"judge failed: {e}")
        return rec
    claims = [c for c in j.claims if c.kind == "fact"]  # interpretation needs no citation; only facts are scored
    n = len(claims)
    cited = sum(c.has_citation for c in claims)
    supported = sum(c.verdict == "supported" for c in claims)
    meets = n > 0 and cited == n and supported == n and not j.key_fact_contradictions
    shipped = rec.get("shipped", False)
    rec.update(n_claims=n, n_cited=cited, n_supported=supported, n_interpretations=len(j.claims) - n,
               key_fact_contradictions=j.key_fact_contradictions, meets_metric=meets, passed=shipped and meets,
               bad_shipped=shipped and not meets, judge_cost_usd=jlog.cost_summary()["llm_usd"],
               problems=[f"{c.verdict}{'' if c.has_citation else ' + NO CITATION'}: {c.claim} ({c.reason})" for c in claims
                         if c.verdict != "supported" or not c.has_citation])
    (out_dir / "judge" / f"{run_id}.json").write_text(j.model_dump_json(indent=2))
    return rec


def rejudge(rows: list[dict], cases: list[dict], out_dir: Path) -> list[dict]:
    """Re-score finished jobs with the current judge, without re-running their pipelines."""
    by_id = {c["id"]: c for c in cases}
    for r in rows:
        if not r.get("shipped") or by_id.get(r["case"], {}).get("expect_failure"):
            continue
        run_dir = out_dir / "runs" / f"{r['mode']}-{r['case']}"
        post = run_dir / "final_post.md"
        if not post.exists():
            continue
        for k in ("problems", "key_fact_contradictions", "error"):
            r.pop(k, None)
        score_post(r, post, json.loads((run_dir / "sources.json").read_text()), by_id[r["case"]], out_dir)
        print(f"  rejudged {r['mode']} {r['case']:<26} {'PASS' if r.get('passed') else 'fail'}", flush=True)
    return rows


def summarize(rows: list[dict], mode: str) -> dict:
    r = [x for x in rows if x["mode"] == mode]
    real = [x for x in r if "n_claims" in x]
    tot = lambda k: sum(x.get(k, 0) for x in real)
    costs = [x["cost_usd"] for x in r if "cost_usd" in x]
    return {
        "mode": mode, "cases": len(r), "passed": sum(bool(x.get("passed")) for x in r),
        "shipped": sum(bool(x.get("shipped")) for x in r), "bad_shipped": sum(bool(x.get("bad_shipped")) for x in r),
        "withheld": sum(1 for x in r if not x.get("shipped") and not x["case"].endswith("dead_link")),
        "claims": tot("n_claims"), "cited_pct": round(100 * tot("n_cited") / max(tot("n_claims"), 1), 1),
        "supported_pct": round(100 * tot("n_supported") / max(tot("n_claims"), 1), 1),
        "avg_cost_usd": round(sum(costs) / max(len(costs), 1), 4), "max_cost_usd": round(max(costs or [0]), 4),
        "avg_drafts": round(sum(x.get("drafts", 0) for x in r) / max(len(r), 1), 2),
        "crashes": sum(1 for x in r if str(x.get("status", "")).startswith("CRASH")),
    }


def scoreboard(summ: list[dict], rows: list[dict], stamp: str) -> str:
    label = {"day1": "Day 1: single agent", "day2": "Day 2: 4 roles + checker"}
    md = [f"# Scoreboard ({stamp})", "", f"Models: pipeline `{config.MODEL}`, checker `{config.CHECKER_MODEL}`, independent judge `{config.JUDGE_MODEL}`.", "",
          "| System | Cases passed | Bad posts shipped | Withheld by checker | Claims cited | Claims supported | Avg drafts | Avg cost/run |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summ:
        md.append(f"| {label[s['mode']]} | **{s['passed']}/{s['cases']}** | {s['bad_shipped']} | {s['withheld']} | {s['cited_pct']}% | "
                  f"{s['supported_pct']}% | {s['avg_drafts']} | ${s['avg_cost_usd']:.4f} |")
    md += ["", "## Per case", "", "| Case | Mode | Status | Claims (cited/supported/total) | Pass | Cost |", "|---|---|---|---|---|---:|"]
    for x in sorted(rows, key=lambda x: (x["case"], x["mode"])):
        cl = f"{x.get('n_cited', '-')}/{x.get('n_supported', '-')}/{x.get('n_claims', '-')}"
        md.append(f"| {x['case']} | {x['mode']} | {str(x.get('status'))[:45]} | {cl} | {'PASS' if x.get('passed') else 'fail'} | ${x.get('cost_usd', 0):.4f} |")
    probs = [x for x in rows if x.get("problems") or x.get("key_fact_contradictions")]
    if probs:
        md += ["", "## Problems the judge found", ""]
        for x in probs:
            md.append(f"**{x['case']} ({x['mode']}, {'shipped' if x.get('shipped') else 'withheld'})**")
            md += [f"- {p}" for p in x.get("problems", [])[:6]] + [f"- KEY FACT CONTRADICTED: {k}" for k in x.get("key_fact_contradictions", [])]
            md.append("")
    return "\n".join(md)


def update_demo(summ: list[dict], stamp: str) -> None:
    if not DEMO.exists():
        return
    by = {s["mode"]: s for s in summ}
    lines = [f"_Auto-filled by `python -m eval.run_eval` on {stamp}. Full table: `eval/results/scoreboard.md`._", "",
             "| | Day 1 (single agent) | Day 2 (4 roles + checker) |", "|---|---:|---:|"]
    def cell(m, k, fmt="{}"):
        return fmt.format(by[m][k]) if m in by else "not run"
    for label, k, fmt in [("Cases passed", "passed", "{}"), ("Bad posts shipped", "bad_shipped", "{}"), ("Withheld by checker", "withheld", "{}"),
                          ("Claims with a source URL", "cited_pct", "{}%"), ("Claims supported (judge)", "supported_pct", "{}%"),
                          ("Avg drafts per run", "avg_drafts", "{}"), ("Avg cost per run", "avg_cost_usd", "${:.4f}")]:
        tot = lambda m: f"/{by[m]['cases']}" if k == "passed" and m in by else ""
        lines.append(f"| {label} | {cell('day1', k, fmt)}{tot('day1')} | {cell('day2', k, fmt)}{tot('day2')} |")
    block = "\n".join(lines)
    txt = DEMO.read_text()
    new = re.sub(r"<!-- SCORES:START -->.*?<!-- SCORES:END -->", f"<!-- SCORES:START -->\n{block}\n<!-- SCORES:END -->", txt, flags=re.S)
    DEMO.write_text(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="day1,day2")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--workers", type=int, default=1, help="parallel runs; keep 1 on Groq free tier")
    ap.add_argument("--resume", help="results folder of an interrupted eval: finished jobs are kept, the rest are run")
    ap.add_argument("--rejudge", action="store_true", help="with --resume: re-score finished jobs with the current judge first")
    args = ap.parse_args()
    config.require_keys(config.LLM_KEY_NAME, "TAVILY_API_KEY")
    config.resolve_models()

    cases = json.loads((ROOT / "test_set.json").read_text())["cases"]
    if args.cases:
        want = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in want]
    modes = args.modes.split(",")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    out_dir = Path(args.resume) if args.resume else ROOT / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "judge").mkdir(exist_ok=True)
    rows_path = out_dir / "rows.jsonl"

    # keep finished jobs from an interrupted eval; re-run crashes (e.g. a rate limit) from scratch
    rows: list[dict] = []
    if rows_path.exists():
        rows = [r for r in (json.loads(l) for l in rows_path.read_text().splitlines() if l.strip())
                if not str(r.get("status", "")).startswith("CRASH") and "judge failed" not in str(r.get("error", ""))]
        rows_path.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))
    if args.rejudge and rows:
        print(f"Re-judging {len(rows)} finished jobs with the current judge...")
        rows = rejudge(rows, cases, out_dir)
        rows_path.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))
    done = {(r["case"], r["mode"]) for r in rows}
    # interleave Day 1 and Day 2 per case, so a partial eval still compares like with like
    jobs = [(c, m) for c in cases for m in modes if (c["id"], m) not in done]
    print(f"{len(done)} jobs already done; running {len(jobs)} ({len(cases)} cases x {modes}) with {args.workers} worker(s) -> {out_dir}")

    stop = {"why": ""}

    def job(cm):
        if stop["why"]:
            return None
        rec = run_case(cm[0], cm[1], out_dir)
        if "DAILY token limit" in str(rec.get("status", "")) + str(rec.get("error", "")):
            stop["why"] = rec["status"]
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(job, jobs):
            if rec is None:
                continue
            if not str(rec.get("status", "")).startswith("CRASH"):
                with rows_path.open("a") as f:
                    f.write(json.dumps(rec, default=str) + "\n")
            rows.append(rec)
            print(f"  {rec['mode']} {rec['case']:<26} {str(rec.get('status'))[:40]:<40} {'PASS' if rec.get('passed') else 'fail'}", flush=True)
    if stop["why"]:
        print(f"\nSTOPPED EARLY: {stop['why'][:300]}\nResume later with:  python -m eval.run_eval --resume {out_dir}")
        rows = [r for r in rows if not str(r.get("status", "")).startswith("CRASH")]

    summ = [summarize(rows, m) for m in modes]
    (out_dir / "results.json").write_text(json.dumps({"stamp": stamp, "summary": summ, "rows": rows}, indent=2, default=str))
    sb = scoreboard(summ, rows, stamp)
    (out_dir / "scoreboard.md").write_text(sb)
    (ROOT / "results" / "scoreboard.md").write_text(sb)
    if set(modes) == {"day1", "day2"} and not args.cases and not stop["why"]:
        update_demo(summ, stamp)
    print("\n" + sb.split("## Per case")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
