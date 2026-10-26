# Scoreboard (2026-10-26 12:18)

Models: pipeline `gpt-4o-mini`, checker `gpt-4.1-mini`, independent judge `gpt-4o`.

| System | Cases passed | Bad posts shipped | Withheld by checker | Claims cited | Claims supported | Avg drafts | Avg cost/run |
|---|---:|---:|---:|---:|---:|---:|---:|
| Day 1: single agent | **11/14** | 3 | 0 | 100.0% | 97.1% | 0.93 | $0.0168 |
| Day 2: 4 roles + checker | **12/14** | 2 | 0 | 100.0% | 98.0% | 2.5 | $0.0248 |

## Per case

| Case | Mode | Status | Claims (cited/supported/total) | Pass | Cost |
|---|---|---|---|---|---:|
| c01_intel_stake | day1 | DONE (unchecked) | 8/8/8 | PASS | $0.0099 |
| c01_intel_stake | day2 | PASSED: ready for human review | 6/6/6 | PASS | $0.0332 |
| c02_nobel_physics_2025 | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0184 |
| c02_nobel_physics_2025 | day2 | PASSED: ready for human review | 5/5/5 | PASS | $0.0366 |
| c03_anthropic_settlement | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0340 |
| c03_anthropic_settlement | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0345 |
| c04_nvidia_5t | day1 | DONE (unchecked) | 7/5/7 | fail | $0.0098 |
| c04_nvidia_5t | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0417 |
| c05_google_chrome_ruling | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0179 |
| c05_google_chrome_ruling | day2 | PASSED: ready for human review | 6/5/6 | fail | $0.0247 |
| c06_louvre_heist | day1 | DONE (unchecked) | 10/10/10 | PASS | $0.0103 |
| c06_louvre_heist | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0179 |
| c07_cloudflare_outage | day1 | DONE (unchecked) | 9/9/9 | PASS | $0.0100 |
| c07_cloudflare_outage | day2 | PASSED: ready for human review | 11/11/11 | PASS | $0.0221 |
| c08_aws_outage | day1 | DONE (unchecked) | 8/7/8 | fail | $0.0182 |
| c08_aws_outage | day2 | PASSED: ready for human review | 9/8/9 | fail | $0.0266 |
| c09_axiom4_shukla | day1 | DONE (unchecked) | 7/7/7 | fail | $0.0101 |
| c09_axiom4_shukla | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0212 |
| c10_meta_scale | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0178 |
| c10_meta_scale | day2 | PASSED: ready for human review | 8/8/8 | PASS | $0.0155 |
| c11_openai_restructure | day1 | DONE (unchecked) | 9/9/9 | PASS | $0.0179 |
| c11_openai_restructure | day2 | PASSED: ready for human review | 9/9/9 | PASS | $0.0298 |
| c12_starship_flight10 | day1 | DONE (unchecked) | 7/7/7 | PASS | $0.0178 |
| c12_starship_flight10 | day2 | PASSED: ready for human review | 7/7/7 | PASS | $0.0173 |
| c13_nobel_chem_2026 | day1 | DONE (unchecked) | 9/9/9 | PASS | $0.0264 |
| c13_nobel_chem_2026 | day2 | PASSED: ready for human review | 9/9/9 | PASS | $0.0187 |
| c14_dead_link | day1 | FAILED: research | -/-/- | PASS | $0.0166 |
| c14_dead_link | day2 | FAILED: research | -/-/- | PASS | $0.0080 |

## Problems the judge found

**c04_nvidia_5t (day1, shipped)**
- unsupported: On October 29, 2025, Nvidia became the first company to achieve a market value of $5 trillion. (The sources do not specify the exact date of October 29, 2025, for Nvidia reaching a $5 trillion market value.)
- unsupported: Nvidia's stock closed at $210, surpassing the $205.76 threshold needed for this milestone. (The sources mention Nvidia's stock topping $210 but do not confirm it closed at $210.)
- KEY FACT CONTRADICTED: On October 29, 2025, Nvidia became the first company to achieve a market value of $5 trillion.

**c05_google_chrome_ruling (day2, shipped)**
- contradicted: On September 2, 2024, U.S. District Judge Amit Mehta ruled that Google does not have to sell its Chrome web browser as part of an antitrust case. (The ruling occurred on September 2, 2025, not 2024.)
- KEY FACT CONTRADICTED: On September 2, 2024, U.S. District Judge Amit Mehta ruled that Google does not have to sell its Chrome web browser as part of an antitrust case.

**c08_aws_outage (day1, shipped)**
- unsupported: This incident affected numerous services, including major platforms like Netflix, Snapchat, and Coinbase, causing widespread disruption. (The sources mention Netflix and other major platforms but do not specifically mention Snapchat and Coinbase.)
- KEY FACT CONTRADICTED: Normal operations were fully restored by 3:01 PM PDT.

**c08_aws_outage (day2, shipped)**
- unsupported: Full recovery took over a day, with normal operations restored by 11:05 AM on October 21. (The sources state that normal operations were fully restored by 3:01 PM PDT on October 20, not October 21.)
- KEY FACT CONTRADICTED: Full recovery took over a day, with normal operations restored by 11:05 AM on October 21

**c09_axiom4_shukla (day1, shipped)**
- KEY FACT CONTRADICTED: The mission lifted off from Launch Complex 39A at 2:31 am ET on June 25.
