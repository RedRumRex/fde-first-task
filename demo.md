# Demo: News to Blog Writer (Task B)

The demo slot is 5 minutes. The speech below takes about 2 minutes, and section 2 lays out how to fill the rest with the live run, the log and the numbers. Every number here comes from real runs on **OpenAI** (`gpt-4o-mini` drafter, `gpt-4.1-mini` checker, `gpt-4o` judge). The final eval run is `eval/results/20261026-121837/`.

---

## 1. The 2-minute speech (about 320 words)

> Lines in *[brackets]* are stage cues.

Hi, I'm Yash. We built **Task B: the news-to-blog writer.**

Our customer is a content team that has to turn breaking news into a blog post quickly. Today a post takes 2 to 3 hours, and about 40 minutes of that is an editor checking every number. The real cost is the error that gets through: a wrong date, an invented statistic, then a public correction.

So our metric isn't "it reads well." It's this: **every claim has a source URL, and an independent judge finds no unsupported claims.**

*[Show the graph in the README.]* It's a LangGraph with four roles. The **researcher** reads the article, then searches and fetches two more outlets. The **drafter** writes in the customer's house style, which we worked out from four of their own blog posts, and tags every sentence as a claim, with its source and a word-for-word quote, or as opinion. The **checker** is a different model with its own prompt, and it has two layers. Plain code checks every number, date and quote against the source, and an LLM judges each claim. If a draft is rejected, the drafter may only fix the flagged sentences, up to three drafts. The **reporter** writes the summary with the exact cost.

*[Start the live run.]* I'm planting a wrong date. The checker rejects it and points to the sentence, and draft two passes.

On 14 test cases, the single agent passed **11** and our four-role system passed **12**. The bigger difference is trust. The single agent invented facts, such as Snapchat and Coinbase in an AWS outage story when no source mentions them. Our system shipped one real mistake: a wrong year.

That's the failure we learned most from. The year "2024" appeared in the source, just in a different sentence, so our number check saw it and passed the claim. We added a rule that checks a date's year against the source. We replayed it on all 52 saved drafts at no cost: it caught that error and nothing else.

Nothing is published automatically; a human editor approves every post. Thank you.

---

## 2. Run-of-show for the 5-minute slot

The five things the brief asks for are marked ✅.

| Time | ✅ What to show | What's on screen | Command / file |
|---|---|---|---|
| 0:00–0:30 | ✅ **Brief and metric** | User, today's cost, success metric | `discovery_brief.md` §1 and §3 |
| 0:30–1:00 | The architecture | Mermaid graph and the four-role table | `README.md` §3 |
| 1:00–2:00 | ✅ **A live run and its log** + ✅ **the checker catching a planted error** | The terminal streaming each agent's steps (about 45s) | `python run.py "https://siliconangle.com/2025/08/22/trump-says-us-government-will-take-10-stake-intel/" --plant date` |
| 2:00–2:30 | Outputs | `report.md` (verdicts per draft, cost table, open doubts), then `final_post.md` with a link on every claim | `runs/<id>/` (printed at the end) |
| 2:30–3:00 | Planted-error suite | Control passes; stat, date and uncited caught by **both** layers; the bonus "disguised" plant caught by the LLM layer | `eval/results/planted_errors.md`, `planted_errors_real_run.md` |
| 3:00–4:00 | ✅ **Day 1 vs Day 2 score** | The table in section 3 and the hand-review notes | `eval/results/scoreboard.md` |
| 4:00–5:00 | ✅ **One failure and the lesson** | Section 5 #1 | — |

**Reference run** (`deliverables/sample_run/`, 44 seconds, $0.017):
- The researcher found 3 sources (siliconangle, pbs, npr) in 15 seconds and stopped on its own.
- Draft 1 was rejected with 6 errors. One was the planted date ("Aug 25"). Others were **mistakes the drafter made on its own**: "$8.9 billion", which no source states, and an evidence quote that isn't in the source. The code layer caught both.
- Draft 2 passed with **9/9 claims verified**.

**What to say during the live run:**
- On `researcher fetch/search`: "The researcher is an agent that chooses what to search for and which pages to open. It can only open links that search actually returned."
- On `plant_error planted`: "Here I'm planting a wrong date."
- On `checker flag … date_not_in_source (deterministic)`: "Plain code caught it: that date isn't in any source."
- On `drafter patch`, then `checker pass`: "The drafter can only change the flagged sentences, so a fix can't break anything else."
- On `COST : $0.0xxx`, point at it.

If the Wi-Fi or the API fails live, open `deliverables/sample_run/log.jsonl` and `report.md` instead.

---

## 3. The numbers

<!-- SCORES:START -->
_Final eval: `eval/results/20261026-121837` (2026-10-26 12:18). Full table: `eval/results/scoreboard.md`._

| | Day 1 (single agent) | Day 2 (4 roles + checker) |
|---|---:|---:|
| Cases passed | 11/14 | **12/14** |
| Bad posts shipped (judge) | 3 | 2 |
| Bad posts shipped (after hand review) | 2 | 1 (now caught by the new date rule) |
| Withheld by checker | 0 | 0 |
| Claims with a source URL | 100.0% | 100.0% |
| Claims supported (judge) | 97.1% | 98.0% |
| Avg drafts per run | 0.93 | 2.5 |
| Avg cost per run | $0.0168 | $0.0248 |
<!-- SCORES:END -->

**How a case is scored:** a case passes when the post ships, 100% of its factual claims carry a source URL, the independent judge (`gpt-4o`, a different model and prompt from the checker) finds 0 unsupported or contradicted claims, and none of the human-checked key facts in `test_set.json` is contradicted. Interpretive sentences ("this signals…") don't need a citation. The dead-link case passes only if the system fails cleanly, and both systems did. The eval (28 runs plus judging) cost **$1.09**.

**Hand review of every post the judge failed:**

| Post | Judge said | Hand review |
|---|---|---|
| Day 1 c04 Nvidia | Unsupported date + "closed at $210" | ❌ **Real**: invented date, and the source only says it traded above $210 |
| Day 1 c08 AWS | "Snapchat and Coinbase" unsupported | ❌ **Real**: no source names them |
| Day 1 c09 Axiom-4 | Launch time contradicts a key fact | ✅ Judge false positive: the post doesn't mention the launch time |
| Day 2 c05 Google | "September 2, **2024**" wrong year | ❌ **Real**: the ruling was in 2025. See section 5 #1. **Fixed and confirmed live**: the re-run says 2025 |
| Day 2 c08 AWS | "restored by 11:05 AM on October 21" | ⚠️ Follows its cited source (ThousandEyes: *"full restoration took until 11:05 AM (UTC) on October 21"*). Another source gives 3:01 PM Oct 20, so the sources disagree. It dropped "(UTC)" |

**Proving the fix:** first for free, by replaying the new year rule on all 52 final drafts saved from the last two evals (no API calls). It flagged **exactly one**, c05, with **zero false alarms**. Then live, by re-running Day 2 on c05 alone with the fixed code ($0.03, `eval/results/20261026-123526/`). The post now says **"September 2, 2025"**. The judge's only remaining flag is that the post says the stock rose **7.2%** (citing Reuters) while the original article and our key fact say **7.5%** (AFP). That's a real disagreement between sources, and `report.md` lists it for the editor under *Open doubts*: "S1 stating 7.5% and S2 stating 7.2%".

**Against the targets in the discovery brief:**

| Target (from `discovery_brief.md`) | Result | |
|---|---|---|
| ≥ 10 of 13 news cases pass | Day 2: **11 of 13** news cases (+ dead link handled) | ✅ |
| 0 bad posts shipped | 1 real error in the scored run (a wrong year), now caught by the new rule | ⚠️ met only after the fix |
| Planted errors caught, control passes | 3/3 required + bonus, on both fixture and real draft | ✅ |
| Cost < $0.05 per run | $0.025 | ✅ |
| Dead link fails cleanly | yes | ✅ |

**Planted errors** (`eval/results/planted_errors.md` on the fixture, `planted_errors_real_run.md` on the real approved draft; same result on both):

| Plant | Example | Result | Caught by |
|---|---|---|---|
| Control (clean draft) | — | PASS, no false alarm | — |
| Invented statistic | "Analysts estimate … revenue by 47%", with a real-looking citation | CAUGHT | code + LLM |
| Wrong date | "August 22" → "August 25" | CAUGHT | code + LLM |
| Uncited claim | "The CEO … will step down" with no source | CAUGHT | code + LLM |
| Bonus: fact disguised as opinion | "Regulators in Europe have already opened an investigation" labelled as opinion | CAUGHT | LLM only |

**How the score moved as we fixed things** (all on OpenAI, same 14 cases):

| Eval round | Day 2 passed | Day 2 withheld | What changed before it |
|---|---:|---:|---|
| 1 | 6/14 | 7 | first version (whole-post rewrites, strict checker) |
| 2 | 10/14 | 3 | patch-only retries, 4-fact minimum, checker prompt tightened |
| 3 | 10/14 | 4 | "sources disagree" becomes an editor note; fuller posts |
| **4 (final)** | **12/14** | **0** | code repairs citations; last-resort salvage of 1–3 failing sentences |

---

## 4. Talking points if they ask "why this design?"

- **Why structured sentences?** It turns "every claim has a source URL" into something code can check. Each sentence is either a claim with IDs and a quote, or an opinion with no facts.
- **Why a deterministic layer?** An LLM checker can let a plausible number through. A regex can't be talked into accepting "47%", and it's free. It also caught the drafter's own "$8.9 billion".
- **Why keep the LLM layer?** It catches what code can't: unsupported claims with no digits, facts disguised as opinion, and wrong attributions.
- **Why fix only the flagged sentences on retry?** Our first version rewrote the whole post each time. That added new errors, and once deleted every fact, so an empty post passed. Now only flagged sentences can change, and a post needs at least 4 cited facts.
- **What's "salvage"?** After 3 drafts, if only 1–3 sentences still fail, code cuts them and the full checker runs again. Cutting an unverified line can't add an error, and the report lists every cut. It's what an editor would do.
- **What about sources that disagree?** The checker marks it `sources_disagree`. The post follows its cited source, and the conflict goes to the editor in `report.md`, rather than blocking a correct post.
- **Why a separate judge?** If the checker graded itself, the score would mean nothing. The judge uses a different model and prompt, and we still check its failures by hand.
- **Cost:** 1.7¢ (Day 1) vs 2.5¢ (Day 2) per run. The exact figure is in each run's `cost.json`.

---

## 5. One failure we found, and what we learned

**Lead with #1.** Use the others if they ask for more.

1. **A wrong year that "was in the source" (final eval, c05).** The post said the Google ruling was on "September 2, **2024**"; it was 2025. Our code layer checks each number against the cited source, and "2024" *was* in the source, but in a different sentence ("found in August 2024 that…"). Our new citation-repair step made it worse by adding another source that also mentioned 2024 elsewhere. **Fix:** a date with a year must match the year the source gives for that date, or the year the source was published. Citation repair now only accepts a source that mentions the number **in a sentence about the same thing**. **Proof without spending:** replaying the rule on all 52 saved drafts flags exactly this one. **Lesson:** "the number appears in the source" isn't the same as "the source says this". Context matters.
2. **The researcher invented a source (first live run).** The model made up an NBC URL. NBC redirected it to a 2023 article about pandas, and a loose relevance check let it in. **Fix:** the researcher can only open links that search returned, plus a whole-word relevance check and a date check. **Lesson:** guard an agent's tools, not just its output.
3. **A PASS with nothing checked.** One checker model returned empty verdicts, and "no verdict" was only a warning, so a draft passed with 2 of 11 claims checked. **Fix:** silence counts as failure: re-ask, then a backup model, then refuse to pass.
4. **The checker blocked correct posts** when the sources disagreed (8 vs 9 Louvre items; "Rs 500 crore" vs "5bn rupees"). **Fix:** a `sources_disagree` verdict that becomes an editor note. The posts withheld for this reason dropped from 3 to 0.
5. **Our own planted test found a bug.** Planting "2022 → 2021" slipped past a 0.1% number tolerance. **Fix:** exact matching. **Lesson:** planted errors test your checker, not just your writer.
6. **Infrastructure.** Groq's free tier allows 8K tokens a minute and 200K a day per model, and OpenAI's free tier 50 requests a day. Both ran out mid-eval. The code picks models your key can actually use, paces itself, resumes interrupted evals, and fails fast with clear errors.

---

## 6. Likely questions

- **"Did splitting into roles help?"** Yes, now: 12/14 vs 11/14, with fewer real errors shipped (1 vs 2), and that 1 is now caught. In earlier rounds it didn't, and the table in section 3 shows how each fix moved it.
- **"What if the sources are wrong?"** We check against sources, not the truth. That's why there are 3 independent outlets and a human approves.
- **"What stops an infinite loop?"** A hard cap of 3 drafts, plus one salvage pass, after which the run fails with every claim that didn't hold up.
- **"How do you know the judge is right?"** We don't fully trust it: every judge failure was checked by hand, and 2 of 5 were wrong or debatable.
- **"Why not re-run the eval after the last fix?"** API budget. We proved the fix by replaying it on the saved drafts, which is free and covers the exact post that failed.
- **"What would you build next?"** Detect syndicated copies of the same wire story, keep units like "(UTC)" in the code check, and have the customer's editors review the tone guide we derived from their blog.

---

## 7. Before you go on

- [ ] `.env` has `LLM_PROVIDER=openai`, `OPENAI_API_KEY` and `TAVILY_API_KEY`
- [ ] Run the live demo command once beforehand (about 45s, about $0.02)
- [ ] Have open: `README.md` (graph), `discovery_brief.md`, `deliverables/sample_run/report.md`, `eval/results/scoreboard.md`, `eval/results/planted_errors.md`
- [ ] Terminal font is large
- [ ] **Backup:** if the live run fails, show `deliverables/sample_run/log.jsonl` and `report.md`
