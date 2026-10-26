"""Per-run logger: every agent's actions go to runs/<run_id>/log.jsonl, artifacts to the same folder,
and token usage is tallied per node so the reporter can state exact cost."""
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


class RunLogger:
    def __init__(self, run_id: str | None = None, base: Path | None = None, quiet: bool = False):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.dir = Path(base or config.RUNS_DIR) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "log.jsonl"
        self.usage: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "models": set()}
        )
        self.tavily_credits = 0.0
        self.t0 = time.time()
        self.quiet = quiet

    # ---- events ----
    def event(self, node: str, kind: str, message: str = "", **data: Any) -> None:
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "elapsed_s": round(time.time() - self.t0, 2),
            "node": node,
            "kind": kind,
            "message": message,
            **data,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        if not self.quiet:
            print(f"[{rec['elapsed_s']:>6.1f}s] {node:<11} {kind:<14} {message}", flush=True)

    def save(self, name: str, content: Any) -> Path:
        path = self.dir / name
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")
        return path

    # ---- cost ----
    def add_usage(self, node: str, model: str, input_tokens: int, output_tokens: int) -> float:
        pin, pout = config.price_for(model)
        cost = input_tokens / 1e6 * pin + output_tokens / 1e6 * pout
        u = self.usage[node]
        u["calls"] += 1
        u["input_tokens"] += input_tokens
        u["output_tokens"] += output_tokens
        u["cost_usd"] += cost
        u["models"].add(model)
        return cost

    def add_tavily(self, credits: float) -> None:
        self.tavily_credits += credits

    def cost_summary(self) -> dict[str, Any]:
        by_node = {
            n: {**{k: v for k, v in u.items() if k != "models"}, "cost_usd": round(u["cost_usd"], 6), "models": sorted(u["models"])}
            for n, u in self.usage.items()
        }
        llm = sum(u["cost_usd"] for u in self.usage.values())
        tav = self.tavily_credits * config.TAVILY_USD_PER_CREDIT
        return {
            "by_node": by_node,
            "input_tokens": sum(u["input_tokens"] for u in self.usage.values()),
            "output_tokens": sum(u["output_tokens"] for u in self.usage.values()),
            "llm_usd": round(llm, 6),
            "tavily_credits": self.tavily_credits,
            "tavily_usd_if_paid": round(tav, 6),
            "total_usd": round(llm + tav, 6),
            "duration_s": round(time.time() - self.t0, 1),
        }
