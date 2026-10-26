"""Run the news-to-blog pipeline on one link.

  python run.py <news_url>                    # Day 2: four agents + checker retry loop
  python run.py <news_url> --plant stat       # plant an error into draft v1 to watch the checker catch it
  python run.py <news_url> --day1             # Day 1: single-agent baseline
  python run.py --graph                       # print the LangGraph as Mermaid
"""
import argparse
import sys

from news2blog import config


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?")
    ap.add_argument("--plant", choices=["stat", "date", "uncited", "disguised"], help="plant an error into the first draft")
    ap.add_argument("--day1", action="store_true", help="run the single-agent baseline instead")
    ap.add_argument("--graph", action="store_true", help="print the graph as Mermaid and exit")
    ap.add_argument("--models", action="store_true", help="list the models your API key can use, and which one each role will get")
    args = ap.parse_args()

    if args.graph:
        from news2blog.graph import build_graph
        print(build_graph().get_graph().draw_mermaid())
        return 0
    if args.models:
        config.require_keys(config.LLM_KEY_NAME)
        avail = config.available_models()
        if config.PROVIDER == "openai":
            avail = [m for m in avail if m.startswith(("gpt-", "o"))]
        print("Available to your key:\n  " + "\n  ".join(avail))
        config.resolve_models()
        return 0
    if not args.url:
        ap.error("url is required")
    config.require_keys(config.LLM_KEY_NAME, "TAVILY_API_KEY")
    config.resolve_models()

    if args.day1:
        from news2blog.baseline import run_baseline
        out = run_baseline(args.url)
    else:
        from news2blog.graph import run_pipeline
        out = run_pipeline(args.url, plant=args.plant)

    print("\n" + "=" * 70)
    print(f"STATUS : {out.get('status')}")
    print(f"COST   : ${out['cost']['total_usd']:.4f}  ({out['cost']['input_tokens']:,} in / {out['cost']['output_tokens']:,} out tokens)")
    print(f"FOLDER : {out['run_dir']}")
    if out.get("final_post_file"):
        print(f"POST   : {out['run_dir']}/{out['final_post_file']}")
    if not args.day1:
        print(f"REPORT : {out['run_dir']}/report.md")
    print(f"LOG    : {out['run_dir']}/log.jsonl")
    return 0 if out.get("status", "").startswith(("PASSED", "DONE")) else 1


if __name__ == "__main__":
    sys.exit(main())
