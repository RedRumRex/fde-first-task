# Demo: News to Blog Writer (Task B)

The demo slot is 5 minutes. The speech below takes about 2 minutes. Section 2 shows how to fill the rest with the live run, the log and the numbers. Every number here comes from real runs on **OpenAI** (`gpt-4o-mini` drafter, `gpt-4.1-mini` checker, `gpt-4o` judge).

---

## 1. The 2-minute speech (about 340 words: speak briskly, or drop the failure paragraph to save 20s)

> Lines in *[brackets]* are stage cues.

Hi, I'm Yash. We built **Task B: the news-to-blog writer.**

Our customer is a content team that has to turn breaking news into a blog post quickly. Right now one post takes 2 to 3 hours, and about 40 minutes of that is an editor checking every number. The real cost is the error that gets through: a wrong date, an invented statistic, then a public correction.

So our metric isn't "it reads well." It's this: **every claim has a source URL, and an independent judge finds no unsupported claims.**

*[Show the graph in the README.]* It's a LangGraph with four roles. The **researcher** reads the article, then searches and fetches two more outlets. The **drafter** writes in our tone guide, and every sentence is tagged as a claim, with its source and a word-for-word quote, or as opinion. The **checker** is a different model with its own prompt, and it has two layers. Plain code checks every number, date and quote against the source, and an LLM judges each claim. A rejected draft goes back for a fix, up to three drafts. The **reporter** writes the summary with the exact cost.

*[Start the live run.]* I'm planting a wrong date. The checker rejects it and points to the sentence, and draft two passes.

On 14 test cases, the single agent passed **11** and our four-role system passed **10**. **So splitting into roles did not raise the pass rate, and I want to be clear about that.** What it changed is trust. The single agent shipped **3** posts with invented facts, like "over 140 AWS services affected". The four-role system's claims were **100%** supported, against 96%. The cost of that is 3 posts held back, and 2.3 cents a run instead of 1.5.

The failure we learned most from: **our checker treats sources that disagree as an error.** Two outlets said 8 stolen items and one said 9, and a good post got held back. The fix is to show disagreements to the editor, not block the post.

Nothing is published automatically; a human editor approves every post. Thank you.

---

## 2. Run-of-show for the 5-minute slot

The five things the brief asks for are marked ✅.

| Time | ✅ What to show | What's on screen | Command / file |
|---|---|---|---|
| 0:00–0:30 | ✅ **Brief and metric** | User, today's cost, success metric | `discovery_brief.md` §1 and §3 |
| 0:30–1:00 | The architecture | Mermaid graph and the four-role table | `README.md` |
| 1:00–2:00 | ✅ **A live run and its log** + ✅ **the checker catching a planted error** | The terminal streaming each agent's steps (takes about 45s) | `python run.py "https://siliconangle.com/2025/08/22/trump-says-us-government-will-take-10-stake-intel/" --plant date` |
| 2:00–2:30 | Outputs | `report.md` (verdicts per draft, cost table, open doubts), then `final_post.md` with a link on every claim | `runs/<id>/` (printed at the end) |
| 2:30–3:00 | Planted-error suite | Control passes; stat, date and uncited all caught by **both** layers; the bonus "disguised" plant caught by the LLM layer | `eval/results/planted_errors.md`, `planted_errors_real_run.md` |
| 3:00–4:00 | ✅ **Day 1 vs Day 2 score** | The table in section 3 and the "what the numbers mean" notes | `eval/results/scoreboard.md` |
| 4:00–5:00 | ✅ **One failure and the lesson** | Section 5 | — |

**Reference run** (`deliverables/sample_run/`, 44 seconds, $0.017):
- The researcher found 3 sources (siliconangle, pbs, npr) in 15 seconds and stopped on its own.
- Draft 1 was rejected with 6 errors. One was the planted date ("Aug 25"). Others were **mistakes the drafter made on its own**: "$8.9 billion", which no source states, and an evidence quote that isn't in the source. The code layer caught both.
- Draft 2 passed with **9/9 claims verified**.

**What to say during the live run:**
- On `researcher fetch/search`: "The researcher is an agent that chooses what to search for and which pages to open. It can only open links that search actually returned."
- On `plant_error planted`: "Here I'm planting a wrong date."
- On `checker flag … date_not_in_source (deterministic)`: "Plain code caught it: that date isn't in any source."
- On `drafter patch` / `revision v2`, then `checker pass`: "The drafter can only change the flagged sentences, so a fix can't break anything else."
- On `COST : $0.0xxx`, point at it.

If the Wi-Fi or the API fails live, open `deliverables/sample_run/log.jsonl` and `report.md` instead.

---

## 3. The numbers

<!-- SCORES:START -->
_Auto-filled by `python -m eval.run_eval` on 2026-10-26 11:33. Full table: `eval/results/scoreboard.md`._

| | Day 1 (single agent) | Day 2 (4 roles + checker) |
|---|---:|---:|
| Cases passed | 11/14 | 10/14 |
| Bad posts shipped | 3 | 1 |
| Withheld by checker | 0 | 3 |
| Claims with a source URL | 100.0% | 100.0% |
| Claims supported (judge) | 96.0% | 100.0% |
| Avg drafts per run | 0.93 | 2.0 |
| Avg cost per run | $0.0145 | $0.0232 |
<!-- SCORES:END -->

**How a case is scored:** a case passes when the post ships, 100% of its factual claims carry a source URL, the independent judge (`gpt-4o`, a different model and prompt from the checker) finds 0 unsupported or contradicted claims, and none of the human-checked key facts in `test_set.json` is contradicted. Interpretive sentences ("this signals…") are labelled as interpretation and don't need a citation. The dead-link case passes only if the system fails cleanly, and both systems did. The whole eval (28 runs plus judging) cost **$0.95**.

**What the numbers mean** (each failure checked by hand):
- **Day 1's bad posts are real hallucinations:**
  - c08 invented "over 140 AWS services" and "Coinbase".
  - c04 invented the exact date and "the stock closed at $210" (the source only says it was trading above $210).
  - c03's flagged date may be a judge mistake: July 20, 2026 was the Monday the article reports.
- **Day 2's one "bad" post (c04) is a judge false positive.** The judge listed the $205.76 key fact as contradicted, but the post simply doesn't mention it, and leaving a key fact out is allowed. So Day 2 shipped no post with a wrong fact.
- **Day 2's 3 held-back posts** (c05, c06, c09) were all rejected for "partial" claims where the **sources disagree with each other**, for example 8 vs 9 Louvre items, and "Rs 500 crore" vs "5bn rupees", which are the same amount. That's the checker being too strict, not the drafter being wrong. See section 5.
- **The brief's "if the split did not improve your score, say so":** it didn't improve the pass rate (10 vs 11). It improved trust: 0 wrong facts shipped (judged by hand) against 2–3, and every claim supported against 96%. It costs about 60% more per run and holds some good posts back.

**Against the targets in the discovery brief:**

| Target (from `discovery_brief.md`) | Result | |
|---|---|---|
| ≥ 10 of 13 news cases pass | Day 2: 9 of 13 news cases (+ dead link handled) | ❌ missed by 1, and all 3 misses were withheld, not wrong |
| 0 bad posts shipped | Day 2: 0 after hand review (the judge's 1 was a false positive) | ✅ |
| Planted errors caught, control passes | 3/3 required + bonus, both fixture and real draft | ✅ |
| Cost < $0.05 per run | $0.023 | ✅ |
| Dead link fails cleanly | yes | ✅ |

**Planted errors** (`eval/results/planted_errors.md` on the fixture, `planted_errors_real_run.md` on the real approved draft; same result on both):

| Plant | Example | Result | Caught by |
|---|---|---|---|
| Control (clean draft) | — | PASS, no false alarm | — |
| Invented statistic | "Analysts estimate … revenue by 47%", with a real-looking citation | CAUGHT | code + LLM |
| Wrong date | "August 22" → "August 25" | CAUGHT | code + LLM |
| Uncited claim | "The CEO … will step down" with no source | CAUGHT | code + LLM |
| Bonus: fact disguised as opinion | "Regulators in Europe have already opened an investigation" labelled as opinion | CAUGHT | LLM only |

---

## 4. Talking points if they ask "why this design?"

- **Why structured sentences?** It turns "every claim has a source URL" into something code can check. Each sentence is either a claim with IDs and a quote, or an opinion with no facts.
- **Why a deterministic layer?** An LLM checker can let a plausible number through. A regex can't be talked into accepting "47%", and it's free. It also caught the drafter's own "$8.9 billion".
- **Why keep the LLM layer?** It catches what code can't: unsupported claims with no digits, facts disguised as opinion, and wrong attributions. The bonus plant shows this.
- **Why fix only the flagged sentences on retry?** Our first version rewrote the whole post on each retry. That added new errors, and once deleted every fact, so an empty post passed. Now only flagged sentences can change, and a post needs at least 4 cited facts.
- **Why a separate judge?** If the checker graded itself, the score would mean nothing. The judge uses a different model and prompt.
- **Why does the reporter not write numbers?** The LLM writes the narrative and code fills in cost and counts, so the report can't make up its own numbers.
- **Cost:** 1.5 cents (Day 1) vs 2.3 cents (Day 2) per run. The exact figure is in each run's `cost.json`.

---

## 5. One failure we found, and what we learned

**Lead with #1, the failure the eval itself showed.** Use the others if they ask for more.

1. **The checker blocks posts when the sources disagree (from the eval).** In 3 of 14 cases a correct post was held back because outlets disagreed, for example 8 vs 9 stolen Louvre items, or the same payment written as "Rs 500 crore" and "5bn rupees". The checker called the sentence "partial" even though it matched its cited source. **Lesson:** a disagreement between sources isn't the drafter's error. It's an open doubt the editor should see. **Next step:** turn source conflicts into a flagged note in the report instead of a rejection. That would likely recover all 3 posts without letting a single invented fact through.
2. **The researcher invented a source (first live run).** The model made up an NBC URL. NBC redirected it to a 2023 article about pandas, and our loose relevance check let it in. **Fix:** the researcher can only open links that search returned, key names must match as whole words, and a source dated far from the original article is rejected. **Lesson:** put guards around an agent's tools, not just its output.
3. **A PASS with nothing checked.** One checker model returned empty verdict lists, and we had treated "no verdict" as a warning, so a draft passed with only 2 of 11 claims checked. **Fix:** silence counts as failure: re-ask, then switch to a backup model, then refuse to pass.
4. **Our own planted test found a bug.** Planting "2022 → 2021" slipped past the code layer, because a 0.1% number tolerance treated the two years as equal. **Fix:** exact matching. **Lesson:** planted errors test your checker, not just your writer.
5. **Infrastructure.** We started on Groq's free tier, whose per-model token limits (8K a minute, 200K a day) ran out halfway through the eval, so we moved to OpenAI. The code switches providers in `.env`, and every error now fails fast with a clear message.

---

## 6. Likely questions

- **"Why is Day 2's pass rate lower?"** It holds back posts when sources disagree (section 5, #1). We'd rather withhold a correct post than ship a wrong one, and the fix is known.
- **"What if the sources are wrong?"** We check against sources, not the truth. That's why there are 3 independent outlets and a human approves.
- **"What stops an infinite loop?"** A hard cap of 3 drafts, after which the run fails with every claim that didn't hold up.
- **"How do you know the judge is right?"** We don't fully trust it, so we checked every failure by hand. That's how we found Day 2's one "bad" post was a judge false positive.
- **"What would you build next?"** Show source conflicts to the editor instead of blocking, detect syndicated copies of the same wire story, and use the customer's real tone guide.

---

## 7. Before you go on

- [ ] `.env` has `LLM_PROVIDER=openai`, `OPENAI_API_KEY` and `TAVILY_API_KEY`
- [ ] Run the live demo command once beforehand to warm up (about 45s)
- [ ] Have open: `README.md` (graph), `discovery_brief.md`, `deliverables/sample_run/report.md`, `eval/results/scoreboard.md`, `eval/results/planted_errors.md`
- [ ] Terminal font is large
- [ ] **Backup:** if the live run fails, show `deliverables/sample_run/log.jsonl` and `report.md`
