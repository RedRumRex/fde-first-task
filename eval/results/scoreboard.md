# Scoreboard (2026-10-26 11:33)

Models: pipeline `gpt-4o-mini`, checker `gpt-4.1-mini`, independent judge `gpt-4o`.

| System | Cases passed | Bad posts shipped | Withheld by checker | Claims cited | Claims supported | Avg drafts | Avg cost/run |
|---|---:|---:|---:|---:|---:|---:|---:|
| Day 1: single agent | **11/14** | 3 | 0 | 100.0% | 96.0% | 0.93 | $0.0145 |
| Day 2: 4 roles + checker | **10/14** | 1 | 3 | 100.0% | 100.0% | 2.0 | $0.0232 |

## Per case

| Case | Mode | Status | Claims (cited/supported/total) | Pass | Cost |
|---|---|---|---|---|---:|
| c01_intel_stake | day1 | DONE (unchecked) | 6/6/6 | PASS | $0.0099 |
| c01_intel_stake | day2 | PASSED: ready for human review | 6/6/6 | PASS | $0.0204 |
| c02_nobel_physics_2025 | day1 | DONE (unchecked) | 8/8/8 | PASS | $0.0185 |
| c02_nobel_physics_2025 | day2 | PASSED: ready for human review | 9/9/9 | PASS | $0.0207 |
| c03_anthropic_settlement | day1 | DONE (unchecked) | 9/8/9 | fail | $0.0261 |
| c03_anthropic_settlement | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0333 |
| c04_nvidia_5t | day1 | DONE (unchecked) | 7/5/7 | fail | $0.0098 |
| c04_nvidia_5t | day2 | PASSED: ready for human review | 9/9/9 | fail | $0.0388 |
| c05_google_chrome_ruling | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0179 |
| c05_google_chrome_ruling | day2 | FAILED: checker rejected all 3 drafts | -/-/- | fail | $0.0186 |
| c06_louvre_heist | day1 | DONE (unchecked) | 10/10/10 | PASS | $0.0103 |
| c06_louvre_heist | day2 | FAILED: checker rejected all 3 drafts | -/-/- | fail | $0.0199 |
| c07_cloudflare_outage | day1 | DONE (unchecked) | 9/9/9 | PASS | $0.0100 |
| c07_cloudflare_outage | day2 | PASSED: ready for human review | 9/9/9 | PASS | $0.0297 |
| c08_aws_outage | day1 | DONE (unchecked) | 10/9/10 | fail | $0.0182 |
| c08_aws_outage | day2 | PASSED: ready for human review | 5/5/5 | PASS | $0.0374 |
| c09_axiom4_shukla | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0101 |
| c09_axiom4_shukla | day2 | FAILED: checker rejected all 3 drafts | -/-/- | fail | $0.0218 |
| c10_meta_scale | day1 | DONE (unchecked) | 6/6/6 | PASS | $0.0097 |
| c10_meta_scale | day2 | PASSED: ready for human review | 8/8/8 | PASS | $0.0119 |
| c11_openai_restructure | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0178 |
| c11_openai_restructure | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0366 |
| c12_starship_flight10 | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0179 |
| c12_starship_flight10 | day2 | PASSED: ready for human review | 6/6/6 | PASS | $0.0166 |
| c13_nobel_chem_2026 | day1 | DONE (unchecked) | 8/8/8 | PASS | $0.0098 |
| c13_nobel_chem_2026 | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0113 |
| c14_dead_link | day1 | FAILED: research | -/-/- | PASS | $0.0166 |
| c14_dead_link | day2 | FAILED: research | -/-/- | PASS | $0.0080 |

## Problems the judge found

**c03_anthropic_settlement (day1, shipped)**
- contradicted: The settlement was approved by U.S. District Judge Araceli Martínez-Olguín on July 20, 2026. (The sources indicate the final approval was granted on April 23, 2025, not July 20, 2026.)
- KEY FACT CONTRADICTED: The settlement was approved by U.S. District Judge Araceli Martínez-Olguín on July 20, 2026.

**c04_nvidia_5t (day1, shipped)**
- unsupported: On October 29, 2025, Nvidia became the first company to achieve a market value of $5 trillion. (The sources do not specify the exact date of October 29, 2025, for Nvidia reaching a $5 trillion market value.)
- unsupported: The company's stock closed at $210, exceeding the $205.76 threshold needed for this valuation. (The sources mention the stock price exceeding $205.76 but do not confirm it closed at $210.)
- KEY FACT CONTRADICTED: On October 29, 2025, Nvidia became the first company to achieve a market value of $5 trillion.

**c04_nvidia_5t (day2, shipped)**
- KEY FACT CONTRADICTED: Nvidia needed a share price of $205.76 for a $5 trillion market value.

**c08_aws_outage (day1, shipped)**
- unsupported: The outage affected over 140 AWS services, disrupting operations for many major platforms including Netflix and Coinbase. (No source specifically states that over 140 AWS services were affected or mentions Coinbase.)
- KEY FACT CONTRADICTED: The post claims the outage affected over 140 AWS services, but no source confirms this number or mentions Coinbase.
