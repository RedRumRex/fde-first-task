# Planted-error tests

- **When:** 2026-10-26 02:13
- **Input:** fixture: Intel stake (eval/fixtures/intel)
- **Checker:** full checker (deterministic + LLM `gpt-4.1-mini`)
- **Result:** ALL REQUIRED PLANTS CAUGHT, control passed
- **Checker cost for this suite:** $0.0069

| Case | Required | What was planted | Checker verdict | Outcome | Caught by |
|---|---|---|---|---|---|
| control | control | Clean draft, no error planted | PASS | **PASS (no false alarm)** | - |
| stat | yes | Invented statistic with a real-looking citation: "Analysts estimate the move will lift revenue by 47% within two years." | REJECT | **CAUGHT** | deterministic, llm |
| date | yes | Wrong date: changed 'August 22' to 'August 25' in [1.1] | REJECT | **CAUGHT** | deterministic, llm |
| uncited | yes | Uncited claim: "The company's chief executive has already said he will step down once the deal closes." | REJECT | **CAUGHT** | deterministic, llm |
| disguised | bonus | Fact disguised as opinion: "Regulators in Europe have already opened a formal investigation into the deal." | REJECT | **CAUGHT** | llm |

## What the checker said

**stat**: Invented statistic with a real-looking citation: "Analysts estimate the move will lift revenue by 47% within two years."
- [1.2] number_not_in_source (deterministic): Number '47' does not appear in any source.
- [1.2] unsupported (llm): No source mentions analysts estimating a 47% revenue lift within two years.

**date**: Wrong date: changed 'August 22' to 'August 25' in [1.1]
- [1.1] date_not_in_source (deterministic): Date 'Aug 25' does not appear in any source.
- [1.1] contradicted (llm): Date is August 22, 2025, not August 25, 2025.

**uncited**: Uncited claim: "The company's chief executive has already said he will step down once the deal closes."
- [3.1] missing_citation (deterministic): Factual claim has no source URL.
- [3.1] unsupported (llm): No source mentions Intel's chief executive stepping down once deal closes.

**disguised**: Fact disguised as opinion: "Regulators in Europe have already opened a formal investigation into the deal."
- [3.4] uncited_fact_in_opinion (llm): Labelled opinion but asserts a fact no source supports. No source mentions regulators in Europe opening a formal investigation into the deal.
