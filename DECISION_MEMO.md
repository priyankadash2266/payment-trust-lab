# Payment Trust Lab — measured investigation memo

**Scope:** Independent synthetic-data portfolio project. Not a real fraud outcome or measured savings.
**Snapshot:** 2026-11-25; same 45-day observation window per payment; evaluation holdout 2026-09.

## Did complaints or fraud grow?

| Cohort | Successes | Contacts | Disputed payments | Affected members | Contacts / 1k successes | Confirmed net loss ₹ | Confirmed loss bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07 | 1220 | 37 | 36 | 35 | 30.33 | 261,703.26 | 130.86 |
| 2026-08 | 1945 | 288 | 217 | 198 | 148.07 | 448,745.70 | 143.1 |
| 2026-09 | 2450 | 120 | 113 | 105 | 48.98 | 1,127,918.22 | 284.99 |

The August complaint spike aligns with a planted posting-delay incident, while September demonstrates increased volume and a higher rate of confirmed synthetic fraud. These are properties of the deterministic generator, not causal claims about a real payment network.

## Retrospective payment-time rules

- Baseline: New device AND amount >= INR 12,000.
- Additional: At least 3 earlier payments in previous hour AND amount >= INR 7,000.
- September successful payment population: **2450**; resolved labels within 45 days: **2125**.
- Baseline reviews: **314**; fraud: **34**; genuine: **234**; unresolved: **46**.
- Combined reviews: **431**; fraud: **44**; genuine: **328**; unresolved: **59**.
- Incremental: **+117** reviews, **+10** confirmed cases, **+94** verified genuine reviews, **+13** unresolved reviews.
- Precision among resolved reviewed: **12.7% → 11.8%**.
- Recall among known-labeled successful payments: **44.2% → 57.1%**.
- Additional historical confirmed net loss covered: **₹153,261.42** (NOT money saved).
- Review budget: **18/day**; busiest combined day **18**; **0** days above budget.

## Recommendation

Trial the proposed velocity rule in shadow mode (without blocking members).

The improved coverage comes with meaningful unnecessary review friction for legitimate multiple-bill payers and lower resolved-label precision. A shadow trial should measure forward-looking alerts, review time, confirmed fraud, unresolved outcomes, and customer contact/escalation rates. Raise the bar for launch if the queue exceeds budget, accuracy deteriorates, or members face meaningful friction.

## Interpretation limits

- Synthetic fraud and genuine labels have unusually complete follow-up; verification bias and unknown cases can still affect results.
- All counts are observational and evaluated with an equal 45-day label and contact arrival window.
- Historical loss covered is potential exposure associated with flagged confirmed cases, not a counterfactual saving.
- The seed process does not provide proof that the proposed rule would work on real CRED traffic.
