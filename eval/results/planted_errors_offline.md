# Planted-error tests

- **When:** 2026-10-25 18:40
- **Input:** fixture: Intel stake (eval/fixtures/intel)
- **Checker:** deterministic layer only
- **Result:** ALL REQUIRED PLANTS CAUGHT, control passed
- **Checker cost for this suite:** $0.0000

| Case | Required | What was planted | Checker verdict | Outcome | Caught by |
|---|---|---|---|---|---|
| control | control | Clean draft, no error planted | PASS | **PASS (no false alarm)** | - |
| stat | yes | Invented statistic with a real-looking citation: "Analysts estimate the move will lift revenue by 47% within two years." | REJECT | **CAUGHT** | deterministic |
| date | yes | Wrong date: changed 'August 22' to 'August 25' in [1.1] | REJECT | **CAUGHT** | deterministic |
| uncited | yes | Uncited claim: "The company's chief executive has already said he will step down once the deal closes." | REJECT | **CAUGHT** | deterministic |
| disguised | bonus | Fact disguised as opinion: "Regulators in Europe have already opened a formal investigation into the deal." | PASS | **n/a offline (needs LLM layer)** | - |

## What the checker said

**stat**: Invented statistic with a real-looking citation: "Analysts estimate the move will lift revenue by 47% within two years."
- [1.2] number_not_in_source (deterministic): Number '47' does not appear in any source.

**date**: Wrong date: changed 'August 22' to 'August 25' in [1.1]
- [1.1] date_not_in_source (deterministic): Date 'Aug 25' does not appear in any source.

**uncited**: Uncited claim: "The company's chief executive has already said he will step down once the deal closes."
- [3.1] missing_citation (deterministic): Factual claim has no source URL.

**disguised**: Fact disguised as opinion: "Regulators in Europe have already opened a formal investigation into the deal."
- (no flags)
