"""Generate a reproducible, data-backed decision memo from the seeded database."""
from pathlib import Path
from .analytics import investigation, evaluate


def generate():
    analytics=investigation()
    rules=evaluate()
    months=analytics['monthly']
    baseline=rules['baseline']
    combined=rules['combined']
    inc=rules['incremental']
    budget_ok=combined['days_over_budget']==0
    recommendation=('Trial the proposed velocity rule in shadow mode (without blocking members).'
                    if budget_ok else 'Revise the proposed rule before trial: the busiest-day queue exceeds budget.')
    fmt=lambda x:f'{x:,.2f}'
    sections=[
      '# Payment Trust Lab — measured investigation memo',
      '',
      '**Scope:** Independent synthetic-data portfolio project. Not a real fraud outcome or measured savings.',
      f'**Snapshot:** {rules["as_of"]}; same {rules["maturity_days"]}-day observation window per payment; evaluation holdout {rules["period"]}.',
      '',
      '## Did complaints or fraud grow?',
      '',
      '| Cohort | Successes | Contacts | Disputed payments | Affected members | Contacts / 1k successes | Confirmed net loss ₹ | Confirmed loss bps |',
      '|---|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for m in months:
        sections.append(f'| {m["period"]} | {m["successful_payments"]} | {m["tickets"]} | {m["disputed_payments"]} | {m["affected_members"]} | {m["contacts_per_1k_successes"]} | {fmt(m["confirmed_net_loss_inr"])} | {m["confirmed_loss_bps"]} |')
    sections += [
      '',
      'The August complaint spike aligns with a planted posting-delay incident, while September demonstrates increased volume and a higher rate of confirmed synthetic fraud. These are properties of the deterministic generator, not causal claims about a real payment network.',
      '',
      '## Retrospective payment-time rules',
      '',
      f'- Baseline: {rules["rules"]["baseline"]}.',
      f'- Additional: {rules["rules"]["proposed"]}.',
      f'- September successful payment population: **{rules["total_successful"]}**; resolved labels within 45 days: **{rules["known_outcomes"]}**.',
      f'- Baseline reviews: **{baseline["reviews"]}**; fraud: **{baseline["confirmed_fraud"]}**; genuine: **{baseline["genuine_reviews"]}**; unresolved: **{baseline["unresolved_reviews"]}**.',
      f'- Combined reviews: **{combined["reviews"]}**; fraud: **{combined["confirmed_fraud"]}**; genuine: **{combined["genuine_reviews"]}**; unresolved: **{combined["unresolved_reviews"]}**.',
      f'- Incremental: **+{inc["reviews"]}** reviews, **+{inc["confirmed_fraud"]}** confirmed cases, **+{inc["genuine_reviews"]}** verified genuine reviews, **+{inc["unresolved_reviews"]}** unresolved reviews.',
      f'- Precision among resolved reviewed: **{baseline["precision"]:.1%} → {combined["precision"]:.1%}**.',
      f'- Recall among known-labeled successful payments: **{baseline["recall"]:.1%} → {combined["recall"]:.1%}**.',
      f'- Additional historical confirmed net loss covered: **₹{fmt(inc["historical_loss_covered_inr"])}** (NOT money saved).',
      f'- Review budget: **{combined["daily_budget"]}/day**; busiest combined day **{combined["busiest_day_reviews"]}**; **{combined["days_over_budget"]}** days above budget.',
      '',
      '## Recommendation',
      '',
      recommendation,
      '',
      'The improved coverage comes with meaningful unnecessary review friction for legitimate multiple-bill payers and lower resolved-label precision. A shadow trial should measure forward-looking alerts, review time, confirmed fraud, unresolved outcomes, and customer contact/escalation rates. Raise the bar for launch if the queue exceeds budget, accuracy deteriorates, or members face meaningful friction.',
      '',
      '## Interpretation limits',
      '',
      '- Synthetic fraud and genuine labels have unusually complete follow-up; verification bias and unknown cases can still affect results.',
      '- All counts are observational and evaluated with an equal 45-day label and contact arrival window.',
      '- Historical loss covered is potential exposure associated with flagged confirmed cases, not a counterfactual saving.',
      '- The seed process does not provide proof that the proposed rule would work on real CRED traffic.',
      ''
    ]
    target=Path(__file__).resolve().parents[1] / 'DECISION_MEMO.md'
    target.write_text('\n'.join(sections),encoding='utf-8')
    print('Wrote', target)
    print(recommendation)

if __name__=='__main__':
    generate()
