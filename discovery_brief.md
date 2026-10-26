# Discovery Brief: News to Blog Writer (Task B)

**Team:** Yashraj Sharma · **Stack:** Python, LangGraph, OpenAI (Groq also supported, switchable in `.env`; the drafter and checker are always different models), Tavily · **Sprint:** AI FDE Fellowship, Sprint 1

## 1. User and workflow

**User:** a content or marketing writer at a tech company who has to publish a quick, sourced blog post when a news story breaks (for example, "Nvidia hits $5 trillion: what it means for AI builders").

**How it's done today:** the writer reads the article, searches for 2 or 3 more sources, writes 600 to 900 words, and then an editor fact-checks it line by line against the sources.

**What that costs:** about 2 to 3 hours per post, and roughly 40 minutes of that is fact-checking. The worst cost is a wrong number or date that gets past the editor: the company has to publish a correction, and readers trust it less.

**What we're replacing:** the research, the first draft and the first line-by-line fact-check. **What we're not replacing:** the editor. A human approves every post, and nothing gets published automatically.

## 2. What good and bad look like

| | Example |
|---|---|
| **Good 1** | "The government will receive 433.3 million shares at $20.47 each [1]" — the number matches the source and links to it. |
| **Good 2** | When sources disagree, the post says so: "Al Jazeera puts the valuation at $500bn [2]" instead of picking one quietly. |
| **Good 3** | Analysis is clearly framed as the blog's own view ("For builders, the bigger story is…") and has no facts slipped into it. |
| **Bad 1** | **Invented statistic:** "Analysts expect a 47% revenue lift" when no source says that, even if a citation is attached. |
| **Bad 2** | **Wrong date:** "Starship flew on August 24" when the source says August 26. |
| **Bad 3** | **Uncited claim posing as opinion:** "Its CEO has already promised to repay the money by 2027" with no source. |

## 3. Success metric

A post is **good** when every factual claim has a source URL **and** an independent judge finds no unsupported or contradicted claims.

| Metric | Target |
|---|---|
| **Primary: case pass rate.** A case passes when 100% of its claims are cited *and* 0 are unsupported. | ≥ 10 of 13 news cases |
| **Trust: bad posts shipped.** A post marked "approved" that still fails the judge. | 0 |
| **Checker: planted errors caught.** | 3 of 3, with the clean control passing (no false alarm) |
| **Cost per run** (LLM + search) | < $0.05 (and $0 on Groq's free tier) |
| **Dead-link case** | Fails cleanly with a report; no post is produced |

The judge is a different prompt and a different model from the checker, so the checker never grades itself. The checker (`gpt-4.1-mini`) is also a different model from the drafter (`gpt-4o-mini`), and the judge is `gpt-4o`. (On Groq the pairing is `gpt-oss-20b` checking `gpt-oss-120b`.) A claim the checker gives no verdict on counts as a failure, never a pass.

### Results against these targets (final eval, run `20261026-121837`)

| Target | Day 2 result | Met? |
|---|---|---|
| ≥ 10 of 13 news cases pass | 11 of 13 (Day 1 single agent: 10 of 13) | ✅ |
| 0 bad posts shipped | Judge flagged 2. Hand review: 1 real error (c05 said "September 2, 2024"; the ruling was in 2025). The other (c08) follows its cited source, which disagrees with another source | ❌ missed, fixed afterwards |
| 3 of 3 planted errors caught, control passes | All caught on the fixture and on a real draft; the clean control passes | ✅ |
| Cost per run < $0.05 | $0.025 (Day 1: $0.017) | ✅ |
| Dead link fails cleanly | Yes, no post produced | ✅ |

**What we did about the miss:** "2024" appeared in the source, but in an unrelated sentence, so checking that "the number is in the source" wasn't enough. A new code rule now requires a full date's year to match the year the source gives for that date (or the source's publication year). Replaying it on all 52 saved drafts flags exactly this one, with no false alarms, and a live re-run of c05 now writes 2025.

## 4. Sources and risks

- **Data:** the input news URL (fetched with httpx and trafilatura) plus 2 more sources found with Tavily search, all on a different domain from the original.
- **Off limits:** getting around paywalls, personal data about private individuals, auto-publishing, and copying long verbatim passages (quotes are capped at about 40 words).
- **Risk 1: a source is wrong.** We check against sources, not against the truth, so "supported" means "a source says so." That's why we need 3 independent sources, and why the editor still approves.
- **Risk 2: syndicated copies.** The same wire story on three sites looks like three sources. We require different domains and the researcher is told to skip copies, but this isn't perfect. It goes in the run report as an open doubt.
- **Risk 3: search finds a different event.** The researcher checks the event's key names against each source, and the checker rejects claims that don't match.
- **When the agent is wrong:** the checker rejects the draft and sends it back up to 2 times. After 3 failed drafts the run stops, and the report lists every claim that didn't hold up. Nothing goes out without a human.

## 5. Smallest version for 2 days

**In:** one URL in, a 350 to 500 word markdown post out, with an inline citation on every claim. Four LangGraph roles with a retry loop (max 3 drafts), a checker with two layers (deterministic number/date/quote checks plus an LLM claim-by-claim check), the run report, JSONL logs with cost, a 14-case test set, a Day 1 single-agent baseline, and 3 planted-error tests.

**Constraint:** cost. The final eval ran on OpenAI with a small budget, so every run had to stay under $0.05 and the full 28-run eval under about $1. We started on Groq's free tier (about 8K tokens/minute per model, sources cut to 3,000 characters); on OpenAI, sources get up to 12,000 characters each.

**Out:** images, SEO, publishing to a CMS, languages other than English, paywalled sources, a UI, and the real tone guide (we're using a placeholder until the customer shares theirs).

## Questions for the customer

1. Who is the reader: developers, buyers or a general audience? This decides the tone.
2. Does a quote or number from the original article alone count as "sourced," or does it need a second source?
3. Are there any outlets you don't want cited, or ones you prefer?
4. What length do you want, and should it have a "what this means for you" section?
5. What turnaround do you need: same hour or same day?
