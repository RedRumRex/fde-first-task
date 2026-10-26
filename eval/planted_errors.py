"""Planted-error tests: prove the checker catches the errors we plant on purpose.

  python -m eval.planted_errors                 # full checker (deterministic + LLM), fixture sources
  python -m eval.planted_errors --offline       # deterministic layer only, no API key needed
  python -m eval.planted_errors --from-run runs/<run_id>   # plant into a real approved draft from a past run

Cases: a clean control (must PASS, proving the checker doesn't just reject everything) plus the 3 required plants
(invented statistic, wrong date, uncited claim) and one bonus (fact disguised as opinion, catchable only by the LLM layer).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from news2blog import config
from news2blog.agents.checker import check_draft
from news2blog.agents.plant import PLANTS
from news2blog.runlog import RunLogger
from news2blog.schemas import BlogDraft

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "intel"
RESULTS = ROOT / "results"
REQUIRED = ["stat", "date", "uncited"]


def load_inputs(from_run: str | None) -> tuple[list[dict], BlogDraft, str]:
    if not from_run:
        return (json.loads((FIXTURE / "sources.json").read_text()), BlogDraft(**json.loads((FIXTURE / "clean_draft.json").read_text())),
                "fixture: Intel stake (eval/fixtures/intel)")
    run = Path(from_run)
    sources = json.loads((run / "sources.json").read_text())
    passing = sorted(p for p in run.glob("check_v*.json") if json.loads(p.read_text())["passed"])
    if not passing:
        raise SystemExit(f"{run} has no checker-approved draft to plant into")
    n = passing[-1].stem.split("_v")[1]
    return sources, BlogDraft(**json.loads((run / f"draft_v{n}.json").read_text())), f"real run {run.name}, approved draft v{n}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="deterministic layer only (no API calls)")
    ap.add_argument("--from-run", help="plant into the approved draft of a previous run")
    args = ap.parse_args()
    use_llm = not args.offline
    if use_llm:
        config.require_keys(config.LLM_KEY_NAME)
        config.resolve_models()

    sources, clean, origin = load_inputs(args.from_run)
    log = RunLogger(run_id="planted-" + datetime.now().strftime("%Y%m%d-%H%M%S"), base=RESULTS / "planted_runs", quiet=True)
    rows, ok = [], True

    cases = [("control", clean, None, "Clean draft, no error planted")]
    for name, fn in PLANTS.items():
        d, ref, desc = fn(clean)
        cases.append((name, d, ref, desc))

    for name, draft, ref, desc in cases:
        try:
            res = check_draft(log, draft, sources, use_llm=use_llm, node=f"checker:{name}")
        except Exception as e:  # e.g. the checker model hit Groq's daily limit: report it, don't crash the suite
            msg = str(e)
            print(f"{name:<10} ERROR   checker unavailable: {msg[:110]}")
            rows.append({"case": name, "required": name in REQUIRED, "planted": desc, "ref": ref, "checker_verdict": "ERROR",
                         "outcome": "NOT RUN (checker unavailable)", "caught_by": [], "flags": [msg[:300]]})
            if name in REQUIRED + ["control"]:  # a bonus case that couldn't run doesn't fail the suite
                ok = False
            if "DAILY token limit" in msg:
                print("Stopping: the checker model is out of daily tokens. Re-run after the reset or on a paid Groq plan.")
                break
            continue
        errs = res.errors()
        on_target = [e for e in errs if e.ref == ref] if ref else []
        if name == "control":
            outcome = "PASS (no false alarm)" if res.passed else "FALSE ALARM"
            good = res.passed
        elif name == "disguised" and not use_llm:
            outcome = "CAUGHT" if on_target else "n/a offline (needs LLM layer)"
            good = True
        else:
            outcome = "CAUGHT" if (not res.passed and on_target) else "MISSED"
            good = outcome == "CAUGHT"
        if name in REQUIRED + ["control"] and not good:
            ok = False
        caught_by = sorted({e.layer for e in on_target})
        rows.append({"case": name, "required": name in REQUIRED, "planted": desc, "ref": ref, "checker_verdict": "PASS" if res.passed else "REJECT",
                     "outcome": outcome, "caught_by": caught_by, "flags": [f"[{e.ref}] {e.type} ({e.layer}): {e.detail}" for e in on_target or errs]})
        print(f"{name:<10} {('REJECT' if not res.passed else 'PASS'):<7} {outcome:<32} {','.join(caught_by)}")

    cost = log.cost_summary()
    RESULTS.mkdir(exist_ok=True)
    mode = "deterministic layer only" if args.offline else f"full checker (deterministic + LLM `{config.CHECKER_MODEL}`)"
    md = [f"# Planted-error tests", "", f"- **When:** {datetime.now():%Y-%m-%d %H:%M}", f"- **Input:** {origin}", f"- **Checker:** {mode}",
          f"- **Result:** {('ALL REQUIRED PLANTS CAUGHT, control passed' + ('' if all(r['outcome'] != 'NOT RUN (checker unavailable)' for r in rows) else ' (a bonus case could not run: checker out of quota)')) if ok else 'FAILURES - see table'}", f"- **Checker cost for this suite:** ${cost['llm_usd']:.4f}", "",
          "| Case | Required | What was planted | Checker verdict | Outcome | Caught by |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['case']} | {'yes' if r['required'] else ('control' if r['case'] == 'control' else 'bonus')} | {r['planted']} | {r['checker_verdict']} | **{r['outcome']}** | {', '.join(r['caught_by']) or '-'} |")
    md += ["", "## What the checker said", ""]
    for r in rows:
        if r["case"] == "control":
            continue
        md.append(f"**{r['case']}**: {r['planted']}")
        md += [f"- {f}" for f in r["flags"][:4]] or ["- (no flags)"]
        md.append("")
    suffix = "_offline" if args.offline else ("_real_run" if args.from_run else "")
    (RESULTS / f"planted_errors{suffix}.md").write_text("\n".join(md), encoding="utf-8")
    (RESULTS / f"planted_errors{suffix}.json").write_text(json.dumps({"origin": origin, "mode": mode, "rows": rows, "cost": cost}, indent=2), encoding="utf-8")
    print(f"\n{'OK' if ok else 'FAILED'}: wrote eval/results/planted_errors{suffix}.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
