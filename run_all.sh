#!/usr/bin/env bash
# Produces every sprint deliverable in one go. Needs GROQ_API_KEY and TAVILY_API_KEY in .env.
# On Groq's free tier this is slow (pacing under ~8K tokens/min per model): expect 1.5-3 hours.
# If the eval hits Groq's daily token cap it stops and prints a --resume command for the next day.
set -euo pipefail
cd "$(dirname "$0")"

DEMO_URL="https://siliconangle.com/2025/08/22/trump-says-us-government-will-take-10-stake-intel/"

echo "== 1/5 offline tests (no API calls) =="
python -m pytest -q

echo "== 2/5 planted-error tests (full checker) =="
python -m eval.planted_errors

echo "== 3/5 sample run with a planted wrong date (the checker should catch it, the drafter should fix it) =="
python run.py "$DEMO_URL" --plant date || true
LATEST=$(ls -td runs/*/ | head -1)
rm -rf deliverables/sample_run && mkdir -p deliverables && cp -r "$LATEST" deliverables/sample_run
echo "copied $LATEST -> deliverables/sample_run"

echo "== 4/5 planted errors on the real approved draft from that run =="
python -m eval.planted_errors --from-run deliverables/sample_run || true

echo "== 5/5 test set: Day 1 vs Day 2 (writes eval/results/scoreboard.md) =="
python -m eval.run_eval --workers 3

echo
echo "Done. Deliverables:"
echo "  discovery_brief.md"
echo "  eval/test_set.json + eval/results/scoreboard.md"
echo "  eval/results/planted_errors.md"
echo "  deliverables/sample_run/report.md, log.jsonl, cost.json"
