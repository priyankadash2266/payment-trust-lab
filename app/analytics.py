"""Investigation SQL and explainable retrospective rule evaluation."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from .db import session

AS_OF = date(2026, 11, 25)
MATURITY_DAYS = 45
REVIEW_BUDGET = 18

# All aggregates are at payment level except contacts; never join two one-to-many
# fact tables and SUM payment amount without first restoring payment grain.
MONTHLY_SQL = """
WITH contact_counts AS (
 SELECT c.payment_id, COUNT(*) AS contacts
 FROM complaints c JOIN payments p ON p.payment_id=c.payment_id
 WHERE DATETIME(c.created_at) BETWEEN DATETIME(p.created_at) AND DATETIME(p.created_at, '+45 days')
   AND DATE(c.created_at) <= DATE(:as_of)
 GROUP BY c.payment_id
),
base AS (
 SELECT strftime('%Y-%m',p.created_at) AS period, p.payment_id,
        p.member_id,p.product_flow,p.status,p.amount_paise,
        COALESCE(c.contacts,0) AS contacts,
        CASE WHEN c.payment_id IS NULL THEN 0 ELSE 1 END AS disputed,
        CASE WHEN o.outcome='confirmed_fraud' AND DATETIME(o.available_at) <= DATETIME(p.created_at,'+45 days') AND DATE(o.available_at) <= DATE(:as_of)
                   THEN o.confirmed_net_loss_paise ELSE 0 END AS confirmed_loss_paise,
        CASE WHEN o.outcome='confirmed_fraud' AND DATETIME(o.available_at) <= DATETIME(p.created_at,'+45 days') AND DATE(o.available_at) <= DATE(:as_of)
                   THEN 1 ELSE 0 END AS confirmed_fraud
 FROM payments p
 LEFT JOIN contact_counts c ON c.payment_id=p.payment_id
 LEFT JOIN outcomes o ON o.payment_id=p.payment_id
 WHERE DATE(p.created_at) <= DATE(:as_of, '-' || :maturity || ' days')
)
SELECT period, COUNT(*) AS payments,
 SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS successful_payments,
 ROUND(SUM(CASE WHEN status='success' THEN amount_paise ELSE 0 END)/100.0,2) AS successful_value_inr,
 SUM(contacts) AS tickets,
 SUM(disputed) AS disputed_payments,
 COUNT(DISTINCT CASE WHEN disputed=1 THEN member_id END) AS affected_members,
 ROUND(1000.0*SUM(contacts)/NULLIF(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),0),2) AS contacts_per_1k_successes,
 ROUND(1000.0*SUM(disputed)/NULLIF(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),0),2) AS disputed_payments_per_1k_successes,
 SUM(confirmed_fraud) AS confirmed_fraud_payments,
 ROUND(SUM(confirmed_loss_paise)/100.0,2) AS confirmed_net_loss_inr,
 ROUND(10000.0*SUM(confirmed_loss_paise)/NULLIF(SUM(CASE WHEN status='success' THEN amount_paise ELSE 0 END),0),2) AS confirmed_loss_bps
FROM base GROUP BY period ORDER BY period;
"""

FLOW_SQL = """
WITH contacts AS (SELECT c.payment_id,COUNT(*) AS n FROM complaints c JOIN payments cp ON cp.payment_id=c.payment_id WHERE DATETIME(c.created_at) BETWEEN DATETIME(cp.created_at) AND DATETIME(cp.created_at,'+45 days') AND DATE(c.created_at) <= DATE(:as_of) GROUP BY c.payment_id)
SELECT strftime('%Y-%m',p.created_at) AS period, p.product_flow,
 COUNT(*) AS payments,
 SUM(CASE WHEN p.status='success' THEN 1 ELSE 0 END) AS successes,
 COALESCE(SUM(c.n),0) AS tickets,
 COUNT(c.payment_id) AS disputed_payments,
 ROUND(1000.0*COALESCE(SUM(c.n),0)/NULLIF(SUM(CASE WHEN p.status='success' THEN 1 ELSE 0 END),0),2) AS contacts_per_1k_successes
FROM payments p LEFT JOIN contacts c ON c.payment_id=p.payment_id
WHERE DATE(p.created_at) <= DATE(:as_of,'-' || :maturity || ' days')
GROUP BY period,p.product_flow ORDER BY period,p.product_flow;
"""

POSTING_SQL = """
WITH posting AS (
 SELECT payment_id,MAX((julianday(occurred_at)-julianday((SELECT created_at FROM payments WHERE payment_id=payment_events.payment_id)))*24) AS hours
 FROM payment_events WHERE event_type='posted' GROUP BY payment_id
), contacts AS (SELECT c.payment_id, COUNT(*) AS n FROM complaints c JOIN payments cp ON cp.payment_id=c.payment_id WHERE DATETIME(c.created_at) BETWEEN DATETIME(cp.created_at) AND DATETIME(cp.created_at,'+45 days') AND DATE(c.created_at) <= DATE(:as_of) GROUP BY c.payment_id)
SELECT strftime('%Y-%m',p.created_at) AS period,
 COUNT(*) AS successful_payments,
 SUM(CASE WHEN posting.payment_id IS NULL THEN 1 ELSE 0 END) AS missing_posting,
 SUM(CASE WHEN posting.hours>24 THEN 1 ELSE 0 END) AS posted_after_24h,
 SUM(CASE WHEN posting.hours>24 THEN COALESCE(contacts.n,0) ELSE 0 END) AS delayed_payment_contacts
FROM payments p LEFT JOIN posting ON posting.payment_id=p.payment_id
LEFT JOIN contacts ON contacts.payment_id=p.payment_id
WHERE p.status='success' AND DATE(p.created_at) <= DATE(:as_of,'-' || :maturity || ' days')
GROUP BY period ORDER BY period;
"""

def rows(db, sql, params=None):
    return [dict(x) for x in db.execute(sql, params or {}).fetchall()]

def investigation():
    with session() as db:
        params={'as_of':AS_OF.isoformat(),'maturity':MATURITY_DAYS}
        return {'as_of':AS_OF.isoformat(),'maturity_days':MATURITY_DAYS,
                'monthly':rows(db,MONTHLY_SQL,params),
                'flows':rows(db,FLOW_SQL,params),
                'posting':rows(db,POSTING_SQL,params)}

def baseline(p):
    """Payment-time only: new device + amount >= INR 12,000."""
    return bool(p['device_new'] and p['amount_paise'] >= 1_200_000)

def proposed(p):
    """Payment-time only: >=3 earlier payments in the preceding hour + >=INR 7,000."""
    return bool(p['payments_last_hour'] >= 3 and p['amount_paise'] >= 700_000)

def _label_known(payment):
    """True when adjudication was available within the common observation window."""
    available = payment['available_at']
    if payment['outcome'] not in ('confirmed_fraud', 'genuine') or not available:
        return False
    payment_date = datetime.fromisoformat(payment['created_at'])
    label_date = datetime.fromisoformat(available)
    return payment_date <= label_date <= payment_date + timedelta(days=MATURITY_DAYS) and label_date.date() <= AS_OF


def evaluate():
    """September holdout: payment-time features, later outcomes for evaluation only."""
    with session() as db:
        data = rows(db, """SELECT p.*,o.outcome,o.available_at,o.confirmed_net_loss_paise
             FROM payments p JOIN outcomes o ON p.payment_id=o.payment_id
             WHERE p.created_at >= '2026-09-01' AND p.created_at < '2026-10-01'
                   AND p.status='success' AND DATE(p.created_at)<=DATE(:as_of,'-45 days')""", {'as_of': AS_OF.isoformat()})

    known_ids = {p['payment_id'] for p in data if _label_known(p)}
    total_known_fraud = sum(p['payment_id'] in known_ids and p['outcome'] == 'confirmed_fraud' for p in data)
    results = {}

    for name, rule in (
        ('baseline', baseline),
        ('combined', lambda p: baseline(p) or proposed(p)),
    ):
        selected = [p for p in data if rule(p)]
        selected_known = [p for p in selected if p['payment_id'] in known_ids]
        fraud = sum(p['outcome'] == 'confirmed_fraud' for p in selected_known)
        genuine = sum(p['outcome'] == 'genuine' for p in selected_known)
        unresolved = len(selected) - len(selected_known)
        alerts_by_day = defaultdict(int)
        for p in selected:
            alerts_by_day[p['created_at'][:10]] += 1
        results[name] = {
            'reviews': len(selected),
            'confirmed_fraud': fraud,
            'genuine_reviews': genuine,
            'unresolved_reviews': unresolved,
            'precision': round(fraud / (fraud + genuine), 4) if fraud + genuine else None,
            'recall': round(fraud / total_known_fraud, 4) if total_known_fraud else None,
            'historical_loss_covered_inr': round(sum(p['confirmed_net_loss_paise'] for p in selected_known if p['outcome'] == 'confirmed_fraud') / 100, 2),
            'busiest_day_reviews': max(alerts_by_day.values(), default=0),
            'days_over_budget': sum(v > REVIEW_BUDGET for v in alerts_by_day.values()),
            'daily_budget': REVIEW_BUDGET,
        }

    before, after = results['baseline'], results['combined']
    keys = ('reviews', 'confirmed_fraud', 'genuine_reviews', 'unresolved_reviews', 'historical_loss_covered_inr')
    incremental = {k: round(after[k] - before[k], 2) if isinstance(after[k], float) else after[k] - before[k] for k in keys}
    return {
        'period': '2026-09',
        'as_of': AS_OF.isoformat(),
        'maturity_days': MATURITY_DAYS,
        'population': 'Successful September payments with >=45 days of follow-up',
        'precision_denominator': 'Reviewed payments with fraud/genuine evidence within 45 days of payment (and by as-of date)',
        'recall_denominator': 'All confirmed fraud with evidence within 45 days among successful holdout payments',
        'total_successful': len(data),
        'known_outcomes': len(known_ids),
        'baseline': before,
        'combined': after,
        'incremental': incremental,
        'rules': {
            'baseline': 'New device AND amount >= INR 12,000',
            'proposed': 'At least 3 earlier payments in previous hour AND amount >= INR 7,000',
        },
        'caveat': 'Observational retrospective coverage, NOT prevented loss, causal impact or measured savings. Synthetic resolved labels are unusually complete relative to real operations.',
    }
